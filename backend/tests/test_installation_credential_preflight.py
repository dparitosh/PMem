"""Exercise the real root installer in a fixture that cannot reach live services."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('mode,store,allowed', [
    ('token','environment',False), ('entra','postgres',False),
    ('disabled','postgres',False), ('token','postgres',True),
])
def test_credential_option_is_validated_before_installation_side_effects(tmp_path, mode, store, allowed):
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Windows PowerShell required')
    windows = tmp_path / 'infra/windows'
    windows.mkdir(parents=True)
    shutil.copyfile(ROOT/'install-depo.ps1', tmp_path/'install-depo.ps1')
    shutil.copyfile(ROOT/'infra/windows/native-install-command.ps1', windows/'native-install-command.ps1')
    (tmp_path/'.env.local').write_text('AUTH_MODE='+mode+'\nDEPO_CREDENTIAL_STORE='+store+'\n')
    (windows/'runtime-config.ps1').write_text(
        "function Read-DepoEnvironment { return @{AUTH_MODE='"+mode+"';DEPO_CREDENTIAL_STORE='"+store+"'} }\n")
    (windows/'deployment-process-guards.ps1').write_text("""
Set-Content -LiteralPath (Join-Path $PSScriptRoot '../../process-guards-imported') -Value 'reached'
function Assert-DepoWindowsManagementAccess { throw 'VALID_OPTION_REACHED_PROCESS_PREFLIGHT' }
function Assert-DepoDeploymentStopped { throw 'Unexpected stopped check' }
""")
    command = "function Get-ExecutionPolicy { 'Bypass' }; & '" + str(tmp_path/'install-depo.ps1').replace("'", "''") + "'"
    result = subprocess.run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-Command',command,
                             '-SkipDependencyInstall','-SkipFrontend','-ReplaceExistingCredentials'],
                            capture_output=True,text=True,timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode != 0  # Valid input deliberately halts at our first process-check stub.
    assert (tmp_path/'process-guards-imported').exists() == allowed
    if allowed:
        assert 'VALID_OPTION_REACHED_PROCESS_PREFLIGHT' in output
    else:
        assert '-ReplaceExistingCredentials requires AUTH_MODE=token and DEPO_CREDENTIAL_STORE=postgres.' in output
    assert 'PostgreSQL schema migration' not in output
    assert not (tmp_path/'data').exists()
