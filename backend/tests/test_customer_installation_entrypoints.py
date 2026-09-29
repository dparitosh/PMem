from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_customer_entrypoints_exist_and_guide_does_not_expose_internal_lifecycle_commands():
    for name in ("configure-depo.ps1", "install-depo.ps1", "diagnose-depo.ps1", "manage-depo.ps1", "certify-depo-release.ps1"):
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


def test_production_dependencies_are_exact_and_hash_pinned():
    lock = (ROOT / "backend" / "requirements-lock.txt").read_text(encoding="utf-8").splitlines()
    entries = [line for line in lock if line and not line.startswith("#")]
    assert len(entries) >= 100
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9.-]*==[^ ]+ --hash=sha256:[0-9a-f]{64}", line) for line in entries)
    installer = (ROOT / "infra" / "windows" / "install-depo.ps1").read_text(encoding="utf-8")
    assert "--require-hashes" in installer
    assert "requirements-lock.txt" in installer


def test_release_certification_requires_external_acceptance_evidence():
    script = (ROOT / "certify-depo-release.ps1").read_text(encoding="utf-8")
    for evidence in ("SupervisorEvidencePath", "BackupRestoreEvidencePath", "BrowserAcceptanceEvidencePath", "RollbackEvidencePath"):
        assert f"[Parameter(Mandatory=$true)][string]${evidence}" in script
    assert "-Phase All" in script
    assert "-Profile Production" in script
