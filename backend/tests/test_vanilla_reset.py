from contextlib import nullcontext
from unittest.mock import Mock
import json
import pytest
from backend.depo_platform import vanilla_reset as resetter


class Database:
    def __init__(self):
        self.statements = []
        self.held = False
        self.fail = False
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def transaction(self): return nullcontext()
    def execute(self, sql, args=()):
        self.statements.append((sql, args))
        self.sql = sql
        if self.fail and sql.startswith('DELETE'):
            raise RuntimeError('database write failure')
    def fetchall(self): return [('agentic_workflow_runs', 3)]
    def fetchone(self): return (int(self.held) if 'legal_hold' in self.sql else 2,)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    for name in ('ONTOLOGY_SERVICE_STORAGE', 'ARTIFACT_STORAGE', 'WORKFLOW_ARTIFACT_ROOT', 'ONTOLOGY_STORAGE_DIR', 'QIF_TASK_ROOT'):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / 'uploads').mkdir()
    (tmp_path / 'uploads/source.xsd').write_text('source')
    foundation = tmp_path / 'backend/ontology_service/resources/foundation'
    foundation.mkdir(parents=True)
    (foundation / 'ido.ttl').write_text('embedded')
    (tmp_path / '.env.local').write_text('credentials retained')
    monkeypatch.setattr('backend.depo_platform.maintenance.invalidate_shared_caches', lambda: True)
    return Database(), tmp_path


def test_preview_is_read_only_and_excludes_credentials(fixture):
    db, root = fixture
    plan = resetter.inventory(db, root)
    assert plan['retained_files']['uploads'] == 1
    assert all(not sql.startswith('DELETE') for sql, _ in db.statements)
    assert 'browser_credential_sessions' in resetter.PRESERVED
    assert not any('credential' in table or 'migration' in table for table in resetter.TABLES)


def test_execute_deletes_owned_data_preserves_foundation_env_and_sql_schema(fixture):
    db, root = fixture
    digest = resetter.inventory(db, root)['preview_digest']
    graph = Mock(return_value={'status': 'SUCCESS'})
    result = resetter.reset(db, root, expected_digest=digest, graph_reset=graph, isolation=lambda _: None)
    assert result['status'] == 'completed'
    assert not (root / 'uploads/source.xsd').exists()
    assert (root / '.env.local').read_text() == 'credentials retained'
    assert (root / 'backend/ontology_service/resources/foundation/ido.ttl').read_text() == 'embedded'
    assert all('DROP ' not in sql and 'TRUNCATE' not in sql for sql, _ in db.statements)
    assert not any('depo_api_credentials' in sql for sql, _ in db.statements)
    assert json.loads(next((root / 'logs/vanilla-reset').glob('vanilla-*.json')).read_text())['status'] == 'completed'
    assert not (root / 'logs/vanilla-reset/active.json').exists()
    graph.assert_called_once()


def test_stale_preview_rejected_before_any_mutation(fixture):
    db, root = fixture
    digest = resetter.inventory(db, root)['preview_digest']
    (root / 'uploads/new.xsd').write_text('new')
    graph = Mock()
    with pytest.raises(ValueError, match='inventory changed'):
        resetter.reset(db, root, expected_digest=digest, graph_reset=graph, isolation=lambda _: None)
    graph.assert_not_called()


@pytest.mark.parametrize('failure', ['graph', 'postgres', 'files'])
def test_partial_failure_receipt_never_claims_success(fixture, monkeypatch, failure):
    db, root = fixture
    digest = resetter.inventory(db, root)['preview_digest']
    db.fail = failure == 'postgres'
    if failure == 'files':
        monkeypatch.setattr(resetter.shutil, 'rmtree', Mock(side_effect=PermissionError('locked')))
    result = resetter.reset(db, root, expected_digest=digest,
                           graph_reset=lambda: {'status': 'FAIL' if failure == 'graph' else 'SUCCESS'}, isolation=lambda _: None)
    assert result['status'] == 'partial'
    assert result['automatic_replay_allowed'] is False
    assert (root / 'logs/vanilla-reset/active.json').exists()
    if failure != 'files': assert (root / 'uploads/source.xsd').exists()


def test_ordinary_runtime_cannot_reset(fixture, monkeypatch):
    monkeypatch.delenv('DEPO_VANILLA_MAINTENANCE', raising=False)
    db, root = fixture
    graph = Mock()
    with pytest.raises(ValueError, match='isolated reset maintenance'):
        resetter.reset(db, root, expected_digest='', graph_reset=graph)
    graph.assert_not_called()


def test_custom_storage_refused_before_deletion(fixture, monkeypatch):
    db, root = fixture
    monkeypatch.setenv('ARTIFACT_STORAGE', str(root.parent))
    with pytest.raises(ValueError, match='unrecognized entries'):
        resetter.inventory(db, root)


def test_configured_external_content_addressed_store_is_scoped_and_previewed(fixture, monkeypatch):
    db, root = fixture
    volume = root.parent / (root.name + '-artifacts')
    directory = volume / 'sha256' / ('a' * 64)
    directory.mkdir(parents=True)
    (directory / 'metadata.json').write_text(json.dumps({'sha256': 'a' * 64}))
    (directory / 'content').write_text('retained content')
    monkeypatch.setenv('ARTIFACT_STORAGE', str(volume))
    plan = resetter.inventory(db, root)
    assert plan['retained_files'][str(volume / 'sha256')] == 2
    result = resetter.reset(db, root, expected_digest=plan['preview_digest'], graph_reset=lambda: {'status': 'SUCCESS'}, isolation=lambda _: None)
    assert result['status'] == 'completed'
    assert volume.exists() and not directory.exists()


def test_external_store_with_unrelated_files_is_never_deleted(fixture, monkeypatch):
    db, root = fixture
    volume = root.parent / (root.name + '-unrelated')
    volume.mkdir()
    retained = volume / 'customer-document.txt'
    retained.write_text('preserve')
    monkeypatch.setenv('ARTIFACT_STORAGE', str(volume))
    graph = Mock()
    with pytest.raises(ValueError, match='unrecognized entries'):
        resetter.reset(db, root, expected_digest='', graph_reset=graph, isolation=lambda _: None)
    graph.assert_not_called()
    assert retained.read_text() == 'preserve'


def test_external_product_folder_name_does_not_establish_ownership(fixture, monkeypatch):
    db, root = fixture
    volume = root.parent / (root.name + '-product-volume')
    products = volume / 'products'
    products.mkdir(parents=True)
    retained = products / 'unrelated.txt'
    retained.write_text('preserve')
    monkeypatch.setenv('ARTIFACT_STORAGE', str(volume))
    with pytest.raises(ValueError, match='product storage contains unrecognized'):
        resetter.inventory(db, root)
    assert retained.read_text() == 'preserve'


def test_legal_hold_blocks_before_graph_deletion(fixture):
    db, root = fixture
    db.held = True
    with pytest.raises(ValueError, match='legal hold'):
        resetter.inventory(db, root)


def test_maintenance_rejects_workflow_writes_and_read_side_effects(monkeypatch):
    monkeypatch.setenv('DEPO_VANILLA_MAINTENANCE', 'true')
    from backend.depo_platform.service_runtime import create_service_app
    from fastapi.testclient import TestClient
    app = create_service_app(title='test', version='1', dependencies=())
    with TestClient(app) as client:
        assert client.post('/api/v1/ontologies/register', json={}).status_code == 503
        assert client.get('/api/v1/ontologies/id/consistency').status_code == 503
        assert client.post('/api/v1/admin/clean-schema', json={}).status_code == 503


def test_process_interruption_leaves_durable_startup_fence(fixture):
    db, root = fixture
    digest = resetter.inventory(db, root)['preview_digest']
    def interrupted(): raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        resetter.reset(db, root, expected_digest=digest, graph_reset=interrupted, isolation=lambda _: None)
    assert (root / 'logs/vanilla-reset/active.json').exists()
    assert not any(sql.startswith('DELETE') for sql, _ in db.statements)


def test_existing_application_worker_blocks_isolated_reset(fixture, monkeypatch):
    import psutil
    from types import SimpleNamespace
    db, root = fixture
    monkeypatch.setenv('DEPO_VANILLA_MAINTENANCE', 'true')
    process = SimpleNamespace(pid=999999, info={'name': 'python.exe'},
                              exe=lambda: str(root / 'backend/.dt_venv/Scripts/python.exe'),
                              cmdline=lambda: ['python', '-m', 'backend.agentic_service.worker'],
                              cwd=lambda: str(root))
    monkeypatch.setattr(psutil, 'process_iter', lambda _: [process])
    with pytest.raises(ValueError, match='Another application Python process'):
        resetter.assert_isolated(root)


def test_reset_endpoints_require_admin_maintenance_dependency():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).parents[1] / 'routes/admin_routes.py').read_text())
    for name in ('preview_vanilla_reset', 'reset_vanilla'):
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        decorators = [ast.unparse(node) for node in function.decorator_list]
        assert any('Depends(require_admin_api_key)' in text for text in decorators)
        assert 'ontology_cleanup' in decorators


@pytest.mark.skipif(__import__('os').name != 'nt', reason='Windows PowerShell launcher contract')
def test_windows_launcher_logs_native_stderr_without_stopping_real_services(tmp_path):
    import subprocess
    from pathlib import Path
    source = Path(__file__).resolve().parents[2]
    scripts = tmp_path / 'infra/windows'
    scripts.mkdir(parents=True)
    for name in ('open-vanilla-maintenance.ps1', 'native-install-command.ps1'):
        (scripts / name).write_bytes((source / 'infra/windows' / name).read_bytes())
    (tmp_path / '.env.local').write_text('# disposable test configuration\n')
    shim = tmp_path / 'fixture-runtime.cmd'
    shim.write_text('@echo off\necho fixture native readiness note 1>&2\nexit /b 0\n')
    (scripts / 'runtime-config.ps1').write_text('function Import-DepoEnvironment { param($Root,$EnvFile) }\n')
    (scripts / 'service-runtimes.ps1').write_text("function Get-DepoServicePython { param($Root,$ServiceId) return '" + str(shim).replace("'", "''") + "' }\n")
    (scripts / 'stop-depo-services.ps1').write_text("param($EnvFile)\nWrite-Host 'fixture stop only'\n")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(scripts / 'open-vanilla-maintenance.ps1')], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    logs = list((tmp_path / 'logs/installation/runs').glob('*.log'))
    assert logs and 'fixture native readiness note' in logs[0].read_text(encoding='utf-8-sig')
    assert not (tmp_path / 'logs/windows-services/vanilla-maintenance.lock').exists()
