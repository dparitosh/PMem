from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
