"""Release boundaries and legacy helper failures, without network or databases."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location('audit_subject', ROOT / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_customer_builders_share_one_policy():
    canonical = load('infra/deployment/build-release-package.py')
    legacy = load('tools/build_customer_release.py')
    for name in ['Setup-DEPO.cmd', 'update-depo.ps1', '.node-version', '.nvmrc',
                 'infra/reasoner/target/generated.jar', 'scripts/load_ontology_to_neo4j.py',
                 'tools/import/run_commit.py', 'docs/audits/review/captured-prompt.json']:
        assert legacy.permitted(name) == canonical.allowed(name)
    assert canonical.allowed('docs/audits/api-crud-inventory-2026-10-10.json')
    assert not canonical.allowed('scripts/load_mbse_xmi_instances.py')


def test_dirty_release_refused_before_zip_creation(tmp_path, monkeypatch):
    module = load('infra/deployment/build-release-package.py')
    required = ['INSTALLATION.md', 'install-depo.ps1', 'infra/deployment/services.json',
                'ontology/bill_of_characteristics.ttl', 'ontology/qif_ap242_boc_alignment.ttl']
    for name in required:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
    entries = ''.join(f'100644 {"0"*40} 0\t{name}\0' for name in required).encode()
    monkeypatch.setattr(module.subprocess, 'check_output', lambda args, **kw: entries if 'ls-files' in args else b'?? backend/new_required.py\0')
    with pytest.raises(ValueError, match='not clean'):
        module.package(tmp_path, tmp_path / 'customer.zip')
    assert not (tmp_path / 'customer.zip').exists()


@pytest.mark.skipif(not (ROOT / 'tools/import/run_commit.py').exists(), reason='Development-only import helper is intentionally excluded from customer packages')
def test_failed_precheck_never_submits_commit(monkeypatch):
    module = load('tools/import/run_commit.py')
    monkeypatch.setattr(module.sys, 'argv', ['run_commit.py', 'task'])
    monkeypatch.setattr(module, 'call_pre_commit', lambda *args: False)
    commit = Mock()
    monkeypatch.setattr(module, 'call_commit', commit)
    assert module.main() == 1
    commit.assert_not_called()


@pytest.mark.skipif(not (ROOT / 'tools/import/upload_only.py').exists(), reason='Development-only import helper is intentionally excluded from customer packages')
def test_upload_rejection_is_failure(tmp_path, monkeypatch):
    module = load('tools/import/upload_only.py')
    source = tmp_path / 'schema.xsd'
    source.write_text('<schema/>')
    monkeypatch.setattr(module, 'DEFAULT', source)
    monkeypatch.setattr(module.requests, 'post', lambda *a, **kw: Mock(ok=False, status_code=403, json=lambda: {'detail': 'Forbidden'}))
    assert module.main() == 1


def test_code_graph_does_not_rank_its_generated_evidence(tmp_path, monkeypatch):
    from tools import code_graph_audit as module
    evidence = tmp_path / 'docs/audits/current/report.json'
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"source": "backend/main.py"}')
    source = tmp_path / 'main.py'
    source.write_text('pass')
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    assert module.files() == [source]
    assert list(module.repository_files({'.json'})) == []


def test_cache_cleanup_reports_denied_paths_and_continues(tmp_path, monkeypatch):
    module = load('infra/deployment/clean-build-caches.py')
    manifest = tmp_path / 'infra/deployment/services.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{}')
    denied = tmp_path / '.pytest_cache'
    allowed = tmp_path / '__pycache__'
    denied.mkdir()
    allowed.mkdir()
    monkeypatch.setattr(module, 'candidates', lambda root: iter([denied, allowed]))
    remove = module.shutil.rmtree

    def cleanup(path):
        if path == denied:
            raise PermissionError('fixture')
        remove(path)

    monkeypatch.setattr(module.shutil, 'rmtree', cleanup)
    result = module.clean(tmp_path, apply=True)
    assert result['failures'] == [{'path': '.pytest_cache', 'error': 'PermissionError'}]
    assert denied.exists() and not allowed.exists()
