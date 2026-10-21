from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def installation_documentation():
    return '\n'.join((ROOT / path).read_text(encoding='utf-8') for path in (
        'INSTALLATION.md', 'docs/installation/OPERATOR_REFERENCE.md'))


def test_customer_guide_is_concise_and_links_complete_operator_reference():
    guide = (ROOT / 'INSTALLATION.md').read_text(encoding='utf-8')
    assert len(guide.splitlines()) < 300
    assert 'docs/installation/OPERATOR_REFERENCE.md' in guide
    assert 'Setup-DEPO.cmd' in guide
    assert '## 1. Prepare the machine' in guide
    assert '## 6. Resolve errors' in guide
    for retired in ('repair-depo-xsd-release.ps1', 'start-zeppelin.ps1'):
        assert not (ROOT / 'infra/windows' / retired).exists()
        assert retired not in installation_documentation()


def test_customer_entrypoints_exist_and_guide_does_not_expose_internal_lifecycle_commands():
    for name in ("configure-depo.ps1", "install-depo.ps1", "diagnose-depo.ps1", "manage-depo.ps1", "certify-depo-release.ps1"):
        assert (ROOT / name).is_file(), name
    for name in ("update-postgres-schema.ps1", "test-postgres-schema.ps1"):
        assert (ROOT / "infra" / "postgres" / name).is_file(), name
        assert not (ROOT / name).exists(), f"duplicate root schema command: {name}"
    guide = installation_documentation()
    assert ".\\install-depo.ps1" in guide
    assert ".\\diagnose-depo.ps1 -Phase All" in guide
    assert ".\\manage-depo.ps1 -Action Start" in guide
    assert "-File .\\infra\\windows\\install-depo-windows.ps1" not in guide
    assert "-File .\\infra\\deployment\\invoke-depo-lifecycle.ps1" not in guide


def test_windows_frontend_has_documented_start_and_stop_lifecycle():
    windows = ROOT / "infra" / "windows"
    for name in ("start-depo-frontend.ps1", "stop-depo-frontend.ps1"):
        assert (windows / name).is_file(), name
    start = (windows / "start-depo-frontend.ps1").read_text(encoding="utf-8")
    assert "frontend\\dist" in start
    assert "frontend.pid" in start
    assert "Get-NetTCPConnection" in start
    guide = installation_documentation()
    assert "-File .\\infra\\windows\\start-depo-frontend.ps1" in guide
    assert "-File .\\infra\\windows\\stop-depo-frontend.ps1" in guide
    for setting in (
        "ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000",
        "DEPO_PIPELINE_EXECUTION_MODE=worker",
        "DEPO_SPARK_ENABLED=false",
        "VITE_API_GATEWAY_URL=",
    ):
        assert setting in guide
    deployment = (ROOT / "config" / "deployment.env.example").read_text(encoding="utf-8")
    assert "DEPO_SPARK_ENABLED=false" in deployment


def test_installer_provisions_neo4j_before_start_and_runs_read_only_preflight_afterward():
    installer = (ROOT / "install-depo.ps1").read_text(encoding="utf-8")
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


def test_schema_only_entrypoints_separate_mutating_and_read_only_operations():
    update = (ROOT / "infra" / "postgres" / "update-postgres-schema.ps1").read_text(encoding="utf-8")
    check = (ROOT / "infra" / "postgres" / "test-postgres-schema.ps1").read_text(encoding="utf-8")
    assert "initialize-depo-schema.ps1" in update
    assert "-CheckOnly" not in update
    assert "initialize-depo-schema.ps1" in check
    assert "-CheckOnly" in check
    for forbidden in ("start-depo-services.ps1", "test-depo-neo4j.ps1", "test-depo-spark.ps1", "npm"):
        assert forbidden not in update
        assert forbidden not in check


def test_diagnostics_include_offline_release_package_integrity():
    diagnostic = (ROOT / "diagnose-depo.ps1").read_text(encoding="utf-8")
    package_check = ROOT / "infra" / "deployment" / "test-installation-package.ps1"
    assert package_check.is_file()
    assert "'Package','Prerequisites','Configuration','Runtime','All'" in diagnostic
    assert "test-installation-package.ps1" in diagnostic
    assert '-CheckPrerequisites -EnvFile $envPath' in diagnostic
    package_text = package_check.read_text(encoding='utf-8')
    assert 'docs/installation/OPERATOR_REFERENCE.md' in package_text


def test_linux_spark_runbook_has_executable_lifecycle_and_safe_configuration():
    linux = ROOT / "infra" / "linux"
    scripts = (
        "configure-depo-linux.sh", "diagnose-depo-linux.sh", "generate-linux-lock.sh",
        "install-depo-linux.sh", "install-spark-linux.sh", "install-systemd-service.sh",
        "start-depo-services.sh", "stop-depo-services.sh", "test-depo-spark.sh",
    )
    for name in scripts:
        source = (linux / name).read_text(encoding="utf-8")
        assert source.startswith("#!/usr/bin/env bash\nset -Eeuo pipefail\n"), name
    configurator = (linux / "configure-depo-linux.sh").read_text(encoding="utf-8")
    assert "openssl rand -hex 32" in configurator
    assert "Refusing to overwrite existing configuration" in configurator
    assert "frontend/.env.local" in configurator
    installer = (linux / "install-depo-linux.sh").read_text(encoding="utf-8")
    assert "requirements-linux-lock.txt" in installer
    assert "--require-hashes" in installer
    guide = installation_documentation()
    assert "Copy-and-paste example: Ubuntu application VM" in guide
    assert "bash infra/linux/configure-depo-linux.sh" in guide
    assert "bash infra/linux/install-spark-linux.sh" in guide
    assert "bash infra/linux/start-depo-services.sh" in guide


def test_customer_installer_forwards_rotation_and_rebuilds_without_installing():
    root = (ROOT / 'install-depo.ps1').read_text(encoding='utf-8')
    assert '[switch]$ReplaceExistingCredentials' in root
    assert '-ReplaceExisting:$ReplaceExistingCredentials' in root
    assert not (ROOT / 'infra/windows/install-depo-windows.ps1').exists()
    installer = (ROOT / 'install-depo.ps1').read_text(encoding='utf-8')
    rebuild = installer.index('if ($SkipDependencyInstall -and -not $SkipFrontend)')
    start = installer.index("Invoke-DepoStage 'Service startup and endpoint validation'")
    assert rebuild < start
    section = installer[rebuild:start]
    assert 'build-depo-frontend.ps1' in section
    assert 'frontend/dist/index.html' in section
    assert 'npm.cmd ci' not in section


def test_manager_orders_frontend_and_backend_and_stops_on_failure(tmp_path):
    import shutil
    import subprocess
    import pytest
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell is required')
    (tmp_path / 'infra/windows').mkdir(parents=True)
    (tmp_path / 'infra/deployment').mkdir(parents=True)
    shutil.copyfile(ROOT / 'manage-depo.ps1', tmp_path / 'manage-depo.ps1')
    shutil.copyfile(ROOT / 'infra/windows/native-install-command.ps1', tmp_path / 'infra/windows/native-install-command.ps1')
    trace = tmp_path / 'trace.txt'
    for phase in ['start','stop']:
        (tmp_path / f'infra/windows/{phase}-depo-frontend.ps1').write_text(f"param([string]$EnvFile)\nAdd-Content -LiteralPath '{trace}' -Value 'frontend-{phase}'\n$global:LASTEXITCODE=0\n")
    lifecycle = tmp_path / 'infra/deployment/invoke-depo-lifecycle.ps1'
    lifecycle.write_text(f"param([string]$Action,[string]$EnvFile,[string]$Profile)\nAdd-Content -LiteralPath '{trace}' -Value ('backend-'+$Action)\n$global:LASTEXITCODE=0\n")
    # This fixture checks ordering, not organization execution policy. The
    # restricted runner cannot import Microsoft.PowerShell.Security; the real
    # child already starts with process Bypass. Isolate that read-only query.
    command="function Get-ExecutionPolicy { 'Bypass' }; & '"+str(tmp_path/'manage-depo.ps1')+"'"
    args=[powershell,'-NoProfile','-ExecutionPolicy','Bypass','-Command',command]
    result=subprocess.run(args+['-Action','Restart'],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert trace.read_text().splitlines() == ['frontend-stop','backend-Stop','backend-Start','frontend-start']
    trace.write_text('')
    lifecycle.write_text(f"param([string]$Action,[string]$EnvFile,[string]$Profile)\nAdd-Content -LiteralPath '{trace}' -Value 'backend-failed'\n$global:LASTEXITCODE=17\n")
    result=subprocess.run(args+['-Action','Start'],capture_output=True,text=True)
    assert result.returncode != 0
    assert trace.read_text().splitlines() == ['backend-failed']
