"""Verify portable toolkit packaging excludes customer-specific state."""
import importlib.util
from pathlib import Path
import shutil
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ods_package', ROOT / 'tools/package_engineering_ods.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_toolkit_archive_contains_only_explicit_source_and_offline_sample(tmp_path):
    source = tmp_path / 'standalone/engineering_ods'
    shutil.copytree(ROOT / 'standalone/engineering_ods', source, ignore=shutil.ignore_patterns('__pycache__'))
    (source / '.env.local').write_text('SECRET=must-not-ship')
    (source / 'load-state.json').write_text('{"ontology_id":"customer-specific"}')
    output = tmp_path / 'toolkit.zip'
    result = module.package(tmp_path, output)
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert len(names) == len(module.FILES)
        assert all(name.startswith('NEXUS-Engineering-ODS-Toolkit/') for name in names)
        assert not any('.env' in name or 'load-state.json' in name for name in names)
    assert result['customer_registration_state_included'] is False
    with pytest.raises(ValueError, match='already exists'): module.package(tmp_path, output)


def test_toolkit_package_rejects_missing_source(tmp_path):
    with pytest.raises(ValueError, match='Incomplete'): module.package(tmp_path, tmp_path / 'toolkit.zip')


def test_customer_release_excludes_media_and_authoring_programs():
    spec = importlib.util.spec_from_file_location('customer_release_boundary', ROOT / 'infra/deployment/build-release-package.py')
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    for name in ['outputs/record_memory_recall.py', 'scripts/videos/record.py', 'scripts/recordings/capture.ps1',
                 'tools/recording/recorder.py', 'tools/video/edit.py', 'scripts/presentations/build_architecture.mjs',
                 'deliverables/video.mp4', '.env.local']:
        assert release.allowed(name) is False
    assert release.allowed('standalone/engineering_ods/nexus_ods.py') is True
