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
