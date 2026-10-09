"""Admin maintenance regression tests without touching a live graph."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def cleaner_class(shared, owned):
    source = Path(__file__).parents[1] / 'Services' / 'neo4j_schema_cleaner.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Neo4jSchemaCleaner')
    original.body = [node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in {'__init__', 'close'}]
    environment = {
        'Driver': object, 'CENTRALIZED_CONFIG_AVAILABLE': True,
        'get_config': lambda: SimpleNamespace(uri='bolt://test', username='test', password='test', database='neo4j'),
        'get_driver': lambda: shared, 'GraphDatabase': SimpleNamespace(driver=lambda *args, **kwargs: owned),
        '_reject_placeholder_uri': lambda uri: None, '_get_env': lambda *keys: 'test', 'logger': MagicMock(),
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[original], type_ignores=[])), str(source), 'exec'), environment)
    return environment['Neo4jSchemaCleaner']


def test_admin_cleaner_does_not_close_shared_service_driver():
    shared, owned = MagicMock(), MagicMock()
    cleaner = cleaner_class(shared, owned)()
    cleaner.close()
    cleaner.close()
    shared.close.assert_not_called()
    owned.close.assert_not_called()


def test_explicit_driver_is_owned_and_closed_once():
    shared, owned = MagicMock(), MagicMock()
    cleaner = cleaner_class(shared, owned)(uri='bolt://explicit', password='test')
    cleaner.close()
    cleaner.close()
    owned.close.assert_called_once()
    shared.close.assert_not_called()


def test_failed_owned_connection_releases_driver():
    shared, owned = MagicMock(), MagicMock()
    owned.session.side_effect = RuntimeError('Connection failed')
    with pytest.raises(RuntimeError, match='Neo4j connection failed'):
        cleaner_class(shared, owned)(uri='bolt://explicit', password='test')
    owned.close.assert_called_once()


def test_database_and_credentials_overrides_are_honored_without_uri():
    shared, owned = MagicMock(), MagicMock()
    cleaner = cleaner_class(shared, owned)(database='isolated', username='custom', password='custom-secret')
    assert cleaner.database == 'isolated'
    assert cleaner.username == 'custom'
    assert cleaner.password == 'custom-secret'
    owned.session.assert_called_with(database='isolated')
    shared.session.assert_not_called()


def test_failed_index_recreation_is_not_success():
    source = Path(__file__).parents[1] / 'Services' / 'neo4j_schema_cleaner.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Neo4jSchemaCleaner')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'reset_database')
    namespace = {'Dict': dict, 'Any': object}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(source), 'exec'), namespace)
    stats = SimpleNamespace(total_nodes=0, total_relationships=0)
    cleaner = SimpleNamespace(get_schema_stats=lambda: stats,
        delete_all_nodes_and_relationships=lambda: (True, 'deleted'),
        drop_all_constraints=lambda: (True, 'dropped'), drop_all_indexes=lambda: (True, 'dropped'),
        create_indexes=lambda: (False, 'index failure'))
    result = namespace['reset_database'](cleaner)
    assert result['status'] == 'FAIL'
    assert result['data_deleted'] is True


def test_maintenance_handler_runs_off_event_loop():
    import asyncio
    import threading
    from functools import wraps
    from starlette.concurrency import run_in_threadpool
    source = Path(__file__).parents[1] / 'routes' / 'admin_routes.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_maintenance_worker')
    namespace = {'wraps': wraps, 'run_in_threadpool': run_in_threadpool}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec'), namespace)
    caller = threading.get_ident()
    result = asyncio.run(namespace['_maintenance_worker'](threading.get_ident)())
    assert result != caller


def test_graph_cache_rejects_other_process_invalidation(monkeypatch):
    from backend.core import graphvis_cache as cache
    from backend.depo_platform import maintenance
    generation = ['initial']
    monkeypatch.setattr(cache, 'GRAPHVIS_CACHE_ENABLED', True)
    monkeypatch.setattr(cache, 'graphvis_cache', {'data': None, 'ts': 0})
    monkeypatch.setattr(maintenance, 'cache_generation', lambda: generation[0])
    cache.store_cached_graph({'nodes': ['old']})
    assert cache.get_cached_graph() == {'nodes': ['old']}
    generation[0] = 'changed-by-another-worker'
    assert cache.get_cached_graph() is None
    cache.store_cached_graph({'nodes': ['new']})
    generation[0] = None
    assert cache.get_cached_graph() is None


def test_graph_reset_invalidates_receipts_without_deleting_governed_catalog(monkeypatch):
    from backend.depo_platform import maintenance, credentials
    from backend import mesh_store
    from contextlib import contextmanager
    statements = []
    class Database:
        rowcount = 2
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def transaction(self): return self
        def cursor(self): return self
        def execute(self, query, params): statements.append((query, params))
    class Registry:
        def __init__(self, namespace): pass
        @contextmanager
        def _connect(self): yield Database()
    monkeypatch.setattr(credentials, 'uses_postgres', lambda: True)
    monkeypatch.setattr(mesh_store, 'PostgresRegistry', Registry)
    result = maintenance.reconcile_graph_reset()
    assert result['invalidated_publications'] == 2
    query, params = statements[0]
    assert query.startswith('UPDATE depo_registry')
    assert params[1] == 'ontology_graph_publications_v1'
    assert params[0].obj['status'] == 'not_published'
    assert params[0].obj['receipt'] is None
    assert result['governed_artifacts_retained'] is True


def test_file_cleanup_reports_partial_failure(tmp_path, monkeypatch):
    from backend.Services.ontology_upload_manager import OntologyUploadManager
    import shutil
    monkeypatch.setattr(OntologyUploadManager, 'ONTOLOGY_STORAGE_DIR', tmp_path)
    monkeypatch.setattr(OntologyUploadManager, 'initialize', classmethod(lambda cls: None))
    (tmp_path / 'retained').mkdir()
    (tmp_path / 'blocked').mkdir()
    original = shutil.rmtree
    def remove(path, *args, **kwargs):
        if path.name == 'blocked':
            raise PermissionError('Locked directory')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(shutil, 'rmtree', remove)
    result = OntologyUploadManager.clear_all_metadata()
    assert result == {'status': 'partial', 'cleared': 1, 'failed': ['blocked']}
    assert (tmp_path / 'blocked').exists()
    assert not (tmp_path / 'retained').exists()
