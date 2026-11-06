import hashlib
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
import sys

from backend.depo_platform import postgres_pool
from backend.depo_platform.operations import operation_scope
from backend.mesh_store import PostgresRegistry
from backend.ontology_service.catalog import OntologyCatalog


def test_deadline_connection_is_reset_and_reused():
    created = []
    class Database:
        closed = False
        info = SimpleNamespace(transaction_status='idle')
        def __init__(self): self.calls = []
        def execute(self, sql, *args): self.calls.append(sql)
        @contextmanager
        def cursor(self): yield self
        def close(self): self.closed = True
    def connect(*args, **kwargs):
        db = Database(); created.append(db); return db
    operation = SimpleNamespace(timeout=lambda value: value)
    with patch.dict(sys.modules, {'psycopg': SimpleNamespace(connect=connect), 'psycopg.pq': SimpleNamespace(TransactionStatus=SimpleNamespace(IDLE='idle'))}):
        with operation_scope(operation):
            for _ in range(2):
                with postgres_pool.connection('performance-reset-test', autocommit=True): pass
        assert len(created) == 1
        assert [sql for sql in created[0].calls if sql.startswith('RESET')] == ['RESET ALL'] * 2
    postgres_pool.close_idle()


def test_registry_bulk_uses_bounded_statements_and_one_transaction(monkeypatch):
    calls = []
    @contextmanager
    def cursor():
        yield SimpleNamespace(execute=lambda *args: calls.append(args))
    @contextmanager
    def transaction(): yield
    @contextmanager
    def connection(): yield SimpleNamespace(transaction=transaction, cursor=cursor)
    registry = PostgresRegistry('performance')
    monkeypatch.setattr(registry, '_connect', connection)
    values = {str(i): {'i': i} for i in range(205)}
    assert registry.put_many(values) == values
    assert len(calls) == 3
    assert all('jsonb_each' in query for query, _ in calls)


def test_failed_timeout_reset_discards_connection():
    from unittest.mock import MagicMock
    database = MagicMock(closed=False, info=SimpleNamespace(transaction_status='idle'))
    database.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError('reset failed')
    modules = {'psycopg': SimpleNamespace(connect=lambda *a, **k: database),
               'psycopg.pq': SimpleNamespace(TransactionStatus=SimpleNamespace(IDLE='idle'))}
    with patch.dict(sys.modules, modules), operation_scope(SimpleNamespace(timeout=lambda value: value)):
        with postgres_pool.connection('failed-reset-test', autocommit=True): pass
    database.close.assert_called_once()


def test_artifact_digest_cache_invalidates_after_replacement(tmp_path, monkeypatch):
    catalog = OntologyCatalog(root=tmp_path)
    folder = tmp_path / 'demo'; folder.mkdir()
    artifact = folder / 'demo.ttl'; artifact.write_bytes(b'first')
    monkeypatch.setattr(catalog, 'get', lambda _: {'artifact_path': str(artifact)})
    assert catalog.artifact_digest('demo') == hashlib.sha256(b'first').hexdigest()
    with patch('hashlib.file_digest', side_effect=AssertionError('unchanged artifact was rehashed')):
        assert catalog.artifact_digest('demo') == hashlib.sha256(b'first').hexdigest()
    artifact.write_bytes(b'replacement')
    assert catalog.artifact_digest('demo') == hashlib.sha256(b'replacement').hexdigest()


def test_catalog_page_delegates_filter_sort_and_limits_to_database(tmp_path, monkeypatch):
    from unittest.mock import Mock
    registry = Mock()
    registry.page.return_value = (450, [{'ontology_id': 'demo'}])
    monkeypatch.setenv('DEPO_DATABASE_URL', 'postgresql://unused/test')
    catalog = OntologyCatalog(root=tmp_path, registry=registry)
    assert catalog.page(limit=200, offset=200) == (450, [{'ontology_id': 'demo'}])
    registry.page.assert_called_once_with(limit=200, offset=200, exclude_superseded=True, order_field='created_at')
    registry.all.assert_not_called()
