"""Exercise registry transaction boundaries without a PostgreSQL server."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch
from backend.mesh_store import PostgresRegistry


class RegistryTransactionTests(unittest.TestCase):
    def test_product_and_approval_roll_back_together(self):
        rows = []
        class DB:
            @contextmanager
            def transaction(self):
                snapshot = list(rows)
                try:
                    yield
                except Exception:
                    rows[:] = snapshot
                    raise
            @contextmanager
            def cursor(self):
                yield self
            def executemany(self, sql, values):
                rows.append(values[0])
                raise RuntimeError('approval write failed')
        @contextmanager
        def connect():
            yield DB()
        registry = PostgresRegistry('data_products')
        with patch.object(registry, '_connect', connect), self.assertRaises(RuntimeError):
            registry.put_with_related('p:1', {'status':'pending_catalog_registration'},
                related_namespace='data_product_approvals', related_key='p:1:approval', related_value={'approved_by':'reviewer'})
        self.assertEqual(rows, [])

    def test_page_uses_bound_json_field_and_database_limits(self):
        queries = []
        class DB:
            @contextmanager
            def transaction(self): yield
            @contextmanager
            def cursor(self): yield self
            def execute(self, sql, values=None): queries.append((sql, values))
            def fetchone(self): return (42,)
            def fetchall(self): return [({'product_id':'one'},)]
        @contextmanager
        def connect(): yield DB()
        registry = PostgresRegistry('catalog_products')
        with patch.object(registry, '_connect', connect):
            total, rows = registry.page(limit=20, offset=10, field='domain', value='engineering', exclude_latest=True, order_field='updated_at')
        self.assertEqual(total, 42)
        self.assertEqual(rows, [{'product_id':'one'}])
        self.assertEqual(queries[-1][1], ['catalog_products','domain','engineering','updated_at',20,10])
        self.assertIn('LIMIT %s OFFSET %s', queries[-1][0])
        self.assertNotIn('engineering', queries[-1][0])

if __name__ == '__main__': unittest.main()
