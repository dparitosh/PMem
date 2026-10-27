from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_offline_lifecycle_fixture_matches_current_prerequisites():
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Windows PowerShell required')
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(ROOT/'infra/deployment/test-depo-lifecycle.ps1')],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS: lifecycle automatic sequence' in result.stdout


@pytest.mark.parametrize('missing', ['Setup-DEPO.cmd', 'infra/windows/setup-depo.ps1', 'infra/windows/install-checkpoints.ps1', 'backend/depo_platform/import_cleanup.py'])
def test_release_gate_rejects_missing_guided_entrypoint(tmp_path, missing):
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Windows PowerShell required')
    validator = tmp_path / 'infra/deployment/test-installation-package.ps1'
    validator.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'infra/deployment/test-installation-package.ps1', validator)
    for relative in ('Setup-DEPO.cmd', 'infra/windows/setup-depo.ps1', 'infra/windows/install-checkpoints.ps1', 'docs/installation/OPERATOR_REFERENCE.md'):
        if relative != missing:
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('')
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(validator)], capture_output=True, text=True)
    assert result.returncode != 0
    assert f'Missing release file: {missing}' in result.stdout + result.stderr


def test_direct_entrypoints_set_process_policy_before_loading_helpers():
    for name in ('infra/windows/setup-depo.ps1', 'install-depo.ps1', 'manage-depo.ps1', 'update-depo.ps1', 'diagnose-depo.ps1'):
        text = (ROOT / name).read_text(encoding='utf-8')
        assert text.index('Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass') < text.index(". (Join-Path")
        assert 'organization policy' in text
        assert '-Scope LocalMachine' not in text


def test_first_setup_validates_before_generating_and_promotes_after_parsing():
    text = (ROOT / 'infra/windows/setup-depo.ps1').read_text(encoding='utf-8')
    assert text.index('foreach($key in @($updates.Keys))') < text.index("new-depo-deployment-config.ps1') -OutputPath $envPath")
    assert text.index('$null=Read-DepoEnvironment -Root $root -EnvFile $envPath') < text.index('Move-Item -LiteralPath $envPath -Destination $finalEnvPath')
    assert "'.setup-'" in text
    assert 'Remove-Item -LiteralPath $stagingDir' in text


def test_portable_postgres_uses_exit_code_wrapper_for_status_and_start():
    text = (ROOT / 'infra/windows/start-depo-postgres.ps1').read_text(encoding='utf-8')
    assert "@('status','-D',$PostgresDataDir) -AllowFailure" in text
    assert "@('start','-D',$PostgresDataDir" in text
    assert '& $pgCtl' not in text


def test_installation_guide_does_not_execute_removed_wrapper():
    text = (ROOT / 'INSTALLATION.md').read_text(encoding='utf-8')
    assert 'infra\\windows\\install-depo-windows.ps1' not in text
    assert 'does not serve the frontend**' not in text
    assert 'First-run connection values are validated' in text


def test_imported_key_list_is_not_nested_by_windows_powershell_pipeline():
    text = (ROOT / 'infra/windows/runtime-config.ps1').read_text(encoding='utf-8')
    assert '$previousNames = ConvertFrom-Json -InputObject $tracked' in text
    assert '$previousNames = @($tracked | ConvertFrom-Json)' not in text


@pytest.mark.parametrize('failure', [False, True])
def test_root_update_preserves_arguments_and_logs_failures(tmp_path, failure):
    import json
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Windows PowerShell required')
    windows = tmp_path / 'infra/windows'
    windows.mkdir(parents=True)
    shutil.copyfile(ROOT / 'update-depo.ps1', tmp_path / 'update-depo.ps1')
    shutil.copyfile(ROOT / 'infra/windows/native-install-command.ps1', windows / 'native-install-command.ps1')
    (tmp_path / '.env.local').write_text('ADMIN_API_KEY=audit-test-secret-123456\n')
    (windows / 'update-depo-windows.ps1').write_text('''param([string]$EnvFile,[string]$Python,[string]$Profile,[switch]$PreflightOnly)
@{EnvFile=$EnvFile;Python=$Python;Profile=$Profile;PreflightOnly=[bool]$PreflightOnly} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot '../../arguments.json')
''' + ("throw 'failure audit-test-secret-123456'" if failure else '$global:LASTEXITCODE=0'))
    command = "function Get-ExecutionPolicy { 'Bypass' }; & '" + str(tmp_path / 'update-depo.ps1').replace("'", "''") + "'"
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command,
                             '-Python', 'SelectedPython', '-EnvFile', 'custom.env', '-Profile', 'Bootstrap', '-PreflightOnly'], capture_output=True, text=True)
    assert (result.returncode != 0) == failure, result.stderr
    arguments = json.loads((tmp_path / 'arguments.json').read_text(encoding='utf-8-sig'))
    assert arguments == {'EnvFile': 'custom.env', 'Python': 'SelectedPython', 'Profile': 'Bootstrap', 'PreflightOnly': True}
    log = next((tmp_path / 'logs/installation/runs').glob('*.log')).read_text(encoding='utf-8')
    assert 'audit-test-secret-123456' not in log
    events = [json.loads(line) for line in next((tmp_path / 'logs/installation/runs').glob('*.jsonl')).read_text(encoding='utf-8').splitlines()]
    assert events[-1]['level'] == ('failed' if failure else 'succeeded')
