import sys
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from backend.depo_platform import postgres_pool


class PoolTests(unittest.TestCase):
    def test_reuse_discards_failed_or_nonidle_connections_without_replay(self):
        created=[]
        class Database:
            closed=False
            def __init__(self): self.info=SimpleNamespace(transaction_status='idle')
            def close(self): self.closed=True
        def connect(*args,**kw):
            db=Database(); created.append(db); return db
        with patch.dict(sys.modules,{'psycopg':SimpleNamespace(connect=connect),'psycopg.pq':SimpleNamespace(TransactionStatus=SimpleNamespace(IDLE='idle'))}):
            for _ in range(2):
                with postgres_pool.connection('test-pool-reuse',autocommit=True) as db: pass
            self.assertEqual(len(created),1)
            with self.assertRaises(ValueError):
                with postgres_pool.connection('test-pool-reuse',autocommit=True): raise ValueError('SQL failed')
            self.assertTrue(created[0].closed)
            with postgres_pool.connection('test-pool-reuse',autocommit=True) as db: db.info.transaction_status='transaction'
            self.assertTrue(created[-1].closed)
            self.assertEqual(len(created),2)
        postgres_pool.close_idle()


if __name__ == '__main__': unittest.main()
