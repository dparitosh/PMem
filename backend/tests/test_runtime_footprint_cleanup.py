import importlib.util
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]


def tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'infra/deployment' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_and_ocr_locks_equal_their_declared_dependency_closures():
    builder = tool('build-service-locks')
    footprint = tool('runtime-footprint')
    metadata = json.loads((ROOT / 'backend/dependency-profiles/windows-metadata.json').read_text())
    def roots(name):
        return [line.strip() for line in (ROOT / 'backend' / name).read_text().splitlines()
                if line.strip() and not line.startswith(('#', '-r'))]
    base = footprint.lock_names(ROOT / 'backend/requirements-lock.txt')
    overlay = footprint.lock_names(ROOT / 'backend/requirements-ocr-lock.txt')
    assert base == set(builder.resolve(roots('requirements.txt'), metadata))
    assert base | overlay == set(builder.resolve(roots('requirements.txt') + roots('requirements-ocr.txt'), metadata))
    assert 'opencv-python-headless' not in base
    assert 'opencv-python' in base  # Required by pinned Semantica metadata.


def test_cache_cleanup_preserves_runtime_artifacts_and_venvs(tmp_path):
    cleaner = tool('clean-build-caches')
    (tmp_path / 'infra/deployment').mkdir(parents=True)
    (tmp_path / 'infra/deployment/services.json').write_text('{}')
    paths = ['backend/__pycache__/module.pyc', '.pytest_cache/lastfailed',
             'uploads/__pycache__/retained.xml', 'data/artifact.json', 'logs/failure.log',
             'backend/.dt_venv/Lib/__pycache__/dependency.pyc', 'frontend/dist/assets/app.js',
             'frontend/node_modules/.vite/dependency.js']
    for name in paths:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('preserve or regenerate')
    preview = cleaner.clean(tmp_path)
    assert preview['applied'] is False
    assert (tmp_path / paths[0]).exists()
    result = cleaner.clean(tmp_path, apply=True)
    assert len(result['caches']) == 2
    for name in paths[:2]:
        assert not (tmp_path / name).exists()
    for name in paths[2:]:
        assert (tmp_path / name).exists()


def test_release_excludes_generated_evidence_but_keeps_authored_docs_and_mappings():
    release = tool('build-release-package')
    for name in ['docs/audits/review/captured-prompt.json', 'docs/audits/review/results.xml',
                 'docs/audits/review/screenshot.png', 'frontend/.vite/cache.json']:
        assert not release.allowed(name)
    for name in ['docs/audits/review.md', 'data/ceim/mapping-packs/ap242.json',
                 'backend/ontology_service/resources/foundation/manifest.json']:
        assert release.allowed(name)
