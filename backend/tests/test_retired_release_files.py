"""Exercise the real upgrade cleanup only inside disposable release fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def retired_fixture(tmp_path):
    shell = shutil.which('powershell.exe')
    if not shell: pytest.skip('Windows PowerShell required')
    scripts = tmp_path / 'infra/windows'
    scripts.mkdir(parents=True)
    deployment = tmp_path / 'infra/deployment'
    deployment.mkdir()
    (tmp_path / 'install-depo.ps1').write_text('# fixture root')
    script = scripts / 'remove-retired-release-files.ps1'
    shutil.copyfile(ROOT / 'infra/windows/remove-retired-release-files.ps1', script)
    def invoke(entries, check=False):
        (deployment / 'retired-files.json').write_text(json.dumps({'schema_version': 1, 'files': entries}))
        command = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-Root', str(tmp_path)]
        if check: command.append('-CheckOnly')
        return subprocess.run(command, capture_output=True, text=True, timeout=30)
    return invoke


def test_upgrade_preflight_keeps_files_and_apply_removes_only_matching_vendor_hash(tmp_path, retired_fixture):
    vendor = tmp_path / 'old.py'
    custom = tmp_path / 'custom.py'
    vendor.write_bytes(b'old vendor code\n')
    custom.write_bytes(b'customer customization\n')
    known = hashlib.sha256(vendor.read_bytes()).hexdigest()
    entries = [{'path': 'old.py', 'sha256': [known]}, {'path': 'custom.py', 'sha256': [known]}]
    checked = retired_fixture(entries, check=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert vendor.exists() and custom.exists()
    result = retired_fixture(entries)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not vendor.exists()
    assert custom.read_bytes() == b'customer customization\n'
    assert 'Preserved customized' in result.stdout


@pytest.mark.parametrize('path', ['../outside.py', 'C:/outside.py', 'infra/../../outside.py'])
def test_upgrade_cleanup_rejects_paths_outside_release(tmp_path, retired_fixture, path):
    result = retired_fixture([{'path': path, 'sha256': ['0' * 64]}])
    assert result.returncode != 0
    assert 'Unsafe retired-file path' in result.stderr


def test_upgrade_cleanup_refuses_directories(tmp_path, retired_fixture):
    (tmp_path / 'old-folder').mkdir()
    result = retired_fixture([{'path': 'old-folder', 'sha256': ['0' * 64]}])
    assert result.returncode != 0
    assert (tmp_path / 'old-folder').is_dir()
