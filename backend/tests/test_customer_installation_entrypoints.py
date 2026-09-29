from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_customer_entrypoints_exist_and_guide_does_not_expose_internal_lifecycle_commands():
    for name in ("configure-depo.ps1", "install-depo.ps1", "diagnose-depo.ps1", "manage-depo.ps1"):
        assert (ROOT / name).is_file(), name
    guide = (ROOT / "INSTALLATION.md").read_text(encoding="utf-8")
    assert ".\\install-depo.ps1" in guide
    assert ".\\diagnose-depo.ps1 -Phase All" in guide
    assert ".\\manage-depo.ps1 -Action Start" in guide
    assert "-File .\\infra\\windows\\install-depo-windows.ps1" not in guide
    assert "-File .\\infra\\deployment\\invoke-depo-lifecycle.ps1" not in guide


def test_installer_provisions_neo4j_before_start_and_runs_read_only_preflight_afterward():
    installer = (ROOT / "infra" / "windows" / "install-depo-windows.ps1").read_text(encoding="utf-8")
    provision = installer.index("test-depo-neo4j.ps1') -EnvFile $envPath -Bootstrap")
    start = installer.index("Service startup and endpoint validation")
    preflight = installer.index("Release preflight")
    assert provision < start < preflight


def test_diagnostic_runtime_is_read_only_for_postgres_and_neo4j():
    diagnostic = (ROOT / "diagnose-depo.ps1").read_text(encoding="utf-8")
    release = (ROOT / "infra" / "windows" / "test-depo-release.ps1").read_text(encoding="utf-8")
    assert "test-depo-release.ps1" in diagnostic
    assert "initialize-depo-schema.ps1') -EnvFile $EnvFile -CheckOnly" in release
    assert "test-depo-neo4j.ps1') -EnvFile $EnvFile -Production" in release
    assert "test-depo-neo4j.ps1') -EnvFile $EnvFile -Bootstrap" not in release
