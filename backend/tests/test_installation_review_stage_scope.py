"""Run the real review stages in Windows PowerShell without contacting services."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('mode', ['shared', 'isolated'])
def test_review_stages_resolve_ingestion_runtime_independently(tmp_path, mode):
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Windows PowerShell required')
    windows = tmp_path / 'infra/windows'
    windows.mkdir(parents=True)
    deployment = tmp_path / 'infra/deployment'
    deployment.mkdir()
    shutil.copyfile(ROOT / 'infra/windows/service-runtimes.ps1', windows / 'service-runtimes.ps1')
    shutil.copyfile(ROOT / 'infra/deployment/services.json', deployment / 'services.json')
    harness = tmp_path / 'review-test.ps1'
    harness.write_text(r'''
param($Source, $Root, $Mode)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Installer parse failure' }
$runner = $ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-DepoStage'}, $true)
. ([scriptblock]::Create($runner.Extent.Text))
$stages = @($ast.FindAll({param($n)
  $n -is [System.Management.Automation.Language.CommandAst] -and
  $n.GetCommandName() -eq 'Invoke-DepoStage' -and
  $n.CommandElements[1].Value -in @('Existing ontology upgrade review','AP242 PMI mapping upgrade review (no graph publication)')
}, $true))
if ($stages.Count -ne 2) { throw 'Expected both real review stages' }
$windows = Join-Path $Root 'infra/windows'
$envPath = Join-Path $Root '.env.local'
$settings = @{DEPO_SERVICE_RUNTIME_MODE=$Mode}
$StageOntologyUpdates = $false
$script:calls = @()
function Import-DepoEnvironment { param($Root, $EnvFile) }
function Invoke-DepoNativeCommand {
  param($Executable, $NativeArguments)
  $script:calls += @{executable=$Executable; arguments=@($NativeArguments)}
  $global:LASTEXITCODE = 0
}
$before = (Get-Location).Path
foreach ($stage in $stages) { & ([scriptblock]::Create($stage.Extent.Text)) }
if ((Get-Location).Path -ne $before) { throw 'Review leaked working directory' }
$folder = if ($Mode -eq 'isolated') { '.dt_venv-ingestion' } else { '.dt_venv' }
$expected = [IO.Path]::GetFullPath((Join-Path $Root "backend/$folder/Scripts/python.exe"))
if ($script:calls.Count -ne 2) { throw 'Expected two review commands' }
foreach ($call in $script:calls) {
  if ([IO.Path]::GetFullPath($call.executable) -ne $expected) { throw 'Wrong review interpreter' }
  if ($call.arguments[1] -ne 'backend.depo_platform.ontology_upgrade') { throw 'Wrong module' }
}
if ($script:calls[0].arguments -contains '--ceim-review') { throw 'Wrong inventory arguments' }
if ($script:calls[1].arguments -notcontains '--ceim-review') { throw 'Missing PMI review flag' }
Write-Output 'REVIEW_STAGES_OK'
''', encoding='utf-8')
    result = subprocess.run(
        [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness),
         '-Source', str(ROOT / 'install-depo.ps1'), '-Root', str(tmp_path), '-Mode', mode],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'REVIEW_STAGES_OK' in result.stdout
