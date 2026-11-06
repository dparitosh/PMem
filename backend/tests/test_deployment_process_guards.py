"""Run Windows deployment guards without starting processes or accessing a database."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHELLS = [path for name in ('powershell', 'pwsh') if (path := shutil.which(name))]


@pytest.mark.parametrize('shell', SHELLS)
def test_configuration_changes_and_active_runtime_are_detected(shell, tmp_path):
    script = tmp_path / 'guards.ps1'
    script.write_text(r'''
param([string]$Repository, [string]$Fixture)
$ErrorActionPreference = 'Stop'
. (Join-Path $Repository 'infra/windows/runtime-config.ps1')
. (Join-Path $Repository 'infra/windows/deployment-process-guards.ps1')
$env:PATH = 'C:\Windows;C:\Hadoop\bin\;C:\Tools'
Add-DepoRuntimePath -Directory 'C:\Hadoop\bin'
$sparkPath = $env:PATH
Add-DepoRuntimePath -Directory 'C:\Hadoop\bin'
$sparkPathStable = $sparkPath -ceq $env:PATH
$config = Join-Path $Fixture 'deployment.env'
Set-Content -LiteralPath $config -Value 'ADMIN_API_KEY=first-fixture-key'
$first = Get-DepoConfigurationFingerprint -Root $Fixture -EnvFile $config -Overrides @{BindHost='127.0.0.1'}
$same = Get-DepoConfigurationFingerprint -Root $Fixture -EnvFile $config -Overrides @{BindHost='127.0.0.1'}
$env:GRAPH_QUERY_TIMEOUT_SECONDS = '17'
$inherited = Get-DepoConfigurationFingerprint -Root $Fixture -EnvFile $config -Overrides @{BindHost='127.0.0.1'}
$env:GRAPH_QUERY_TIMEOUT_SECONDS = '18'
$inheritedChanged = Get-DepoConfigurationFingerprint -Root $Fixture -EnvFile $config -Overrides @{BindHost='127.0.0.1'}
$binding = Get-DepoConfigurationFingerprint -Root $Fixture -EnvFile $config -Overrides @{BindHost='10.0.2.16'}
Set-Content -LiteralPath $config -Value 'ADMIN_API_KEY=rotated-fixture-key'
$rotated = Get-DepoConfigurationFingerprint -Root $Fixture -EnvFile $config -Overrides @{BindHost='127.0.0.1'}
function Get-CimInstance { [pscustomobject]@{ExecutablePath='C:/fixture/python.exe'} }
$blocked = $false
try { Assert-DepoRuntimeIdle -Python 'c:/fixture/PYTHON.exe' } catch { $blocked = $true }
Assert-DepoRuntimeIdle -Python 'C:/other/python.exe'
$manifestDirectory = Join-Path $Fixture 'infra/deployment'
New-Item -ItemType Directory -Path $manifestDirectory -Force | Out-Null
Set-Content -LiteralPath (Join-Path $manifestDirectory 'services.json') -Value '{"services":[{"id":"ontology"}],"workers":[]}'
$script:fixtureRuntime = Join-Path $Fixture 'backend/.dt_venv-ontology/Scripts/python.exe'
function Get-CimInstance { [pscustomobject]@{ExecutablePath=$script:fixtureRuntime} }
$installationBlocked = $false
try { Assert-DepoDeploymentStopped -Root $Fixture } catch { $installationBlocked = $true }
@{first=$first; same=$same; inherited=$inherited; inheritedChanged=$inheritedChanged; binding=$binding; rotated=$rotated; blocked=$blocked; installationBlocked=$installationBlocked; sparkPathStable=$sparkPathStable} | ConvertTo-Json -Compress
''', encoding='utf-8')
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                             str(ROOT), str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value['first'] == value['same']
    assert value['sparkPathStable']
    assert value['inherited'] != value['inheritedChanged']
    assert value['first'] != value['binding']
    assert value['first'] != value['rotated']
    assert value['blocked']
    assert value['installationBlocked']
    assert all(len(value[name]) == 64 for name in ('first', 'same', 'binding', 'rotated'))
    assert 'fixture-key' not in result.stdout


def test_startup_checks_runtime_before_database_and_does_not_migrate():
    source = (ROOT / 'infra/windows/start-depo-services.ps1').read_text(encoding='utf-8')
    assert source.index("Missing runtime for") < source.index("'start-depo-postgres.ps1'")
    assert "'initialize-depo-schema.ps1') -EnvFile $EnvFile -CheckOnly" in source
    assert '$startedService.Module $cleanupDeadline' in source


def test_dependency_guard_runs_before_pip():
    source = (ROOT / 'infra/windows/install-depo.ps1').read_text(encoding='utf-8')
    assert source.index('Assert-DepoRuntimeIdle -Python $venvPython') < source.index('Invoke-DepoInstallCommand -Executable')


@pytest.mark.parametrize('shell', SHELLS)
def test_management_prerequisites_report_denied_access_without_bypassing_guards(shell, tmp_path):
    script = tmp_path / 'management-access.ps1'
    script.write_text(r'''
param([string]$Repository)
$ErrorActionPreference = 'Stop'
. (Join-Path $Repository 'infra/windows/deployment-process-guards.ps1')
$script:denyProcesses = $false
$script:denyListeners = $false
function Get-CimInstance {
  if ($script:denyProcesses) { throw 'fixture process access denied' }
  [pscustomobject]@{ExecutablePath='C:/fixture/python.exe'}
}
function Get-NetTCPConnection {
  if ($script:denyListeners) { throw 'fixture listener access denied' }
  # No current listeners is a valid successful query.
}
Assert-DepoWindowsManagementAccess
$script:denyProcesses = $true
$processMessage = ''
try { Assert-DepoWindowsManagementAccess } catch { $processMessage = $_.Exception.Message }
$guardMessage = ''
try { Assert-DepoRuntimeIdle -Python 'C:/fixture/python.exe' } catch { $guardMessage = $_.Exception.Message }
$script:denyProcesses = $false
$script:denyListeners = $true
$listenerMessage = ''
try { Assert-DepoWindowsManagementAccess } catch { $listenerMessage = $_.Exception.Message }
@{process=$processMessage; listener=$listenerMessage; guard=$guardMessage} | ConvertTo-Json -Compress
''', encoding='utf-8')
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(script), str(ROOT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert 'CIM/WMI' in value['process']
    assert 'fixture process access denied' in value['process']
    assert 'Do not bypass' in value['guard']
    assert 'Get-NetTCPConnection' in value['listener']
    assert 'fixture listener access denied' in value['listener']


@pytest.mark.parametrize('shell', SHELLS)
def test_frontend_denied_process_inspection_starts_nothing(shell, tmp_path):
    windows = tmp_path / 'infra' / 'windows'
    windows.mkdir(parents=True)
    for name in ('start-depo-frontend.ps1', 'deployment-process-guards.ps1',
                 'runtime-config.ps1', 'process-control.ps1'):
        shutil.copy2(ROOT / 'infra' / 'windows' / name, windows / name)
    python = tmp_path / 'backend' / '.dt_venv' / 'Scripts' / 'python.exe'
    python.parent.mkdir(parents=True)
    python.touch()
    index = tmp_path / 'frontend' / 'dist' / 'index.html'
    index.parent.mkdir(parents=True)
    index.write_text('<div id="root"></div>', encoding='utf-8')
    script = tmp_path / 'denied-frontend.ps1'
    script.write_text(r'''
param([string]$Fixture)
$ErrorActionPreference = 'Stop'
function Get-CimInstance { throw 'fixture process access denied' }
function Start-Process { throw 'Unexpected process launch' }
$message = ''
try { & (Join-Path $Fixture 'infra/windows/start-depo-frontend.ps1') }
catch { $message = $_.Exception.Message }
@{message=$message; logsCreated=(Test-Path (Join-Path $Fixture 'logs'))} | ConvertTo-Json -Compress
''', encoding='utf-8')
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(script), str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert 'fixture process access denied' in value['message']
    assert 'Unexpected process launch' not in value['message']
    assert not value['logsCreated']
