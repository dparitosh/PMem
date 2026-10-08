import ast
import copy
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from backend.artifact_store import ArtifactStore


class Registry:
    def __init__(self): self.values = {}; self.writes = 0; self.fail_on = None; self.busy = False; self.locks = []
    def get(self, key): return copy.deepcopy(self.values.get(key))
    def put_many(self, values):
        self.writes += 1
        if self.writes == self.fail_on: raise RuntimeError('Database unavailable')
        self.values.update(copy.deepcopy(values))
    @contextmanager
    def advisory_lock(self, key):
        self.locks.append(key)
        yield not self.busy


class RetentionRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.artifacts = ArtifactStore(Path(self.temp.name))
        source = Path(self.temp.name) / 'source.txt'; source.write_text('retained evidence')
        self.artifact_id = self.artifacts.ingest(source)['artifact_id']
        tree = ast.parse(Path('backend/data_catalog_service/artifact_retention.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        namespace = {'datetime':datetime, 'timedelta':timedelta, 'timezone':timezone, 'uuid':uuid,
                     'Any':object, 'TIERS':{'hot', 'warm', 'cold', 'archive'}}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'retention.py', 'exec'), namespace)
        cls = namespace['ArtifactRetentionRegistry']; self.retention = cls.__new__(cls)
        self.retention.store = Registry(); self.retention.artifact_store = self.artifacts
        self.retention.register(self.artifact_id, {'retention_days':1, 'reason':'Approved policy'}, 'steward')
        self.retention._now = lambda: datetime.now(timezone.utc) + timedelta(days=2)

    def test_strict_types(self):
        for changes in [{'retention_days':True}, {'legal_hold':'false'}, {'legal_hold':0}]:
            with self.assertRaises(ValueError):
                self.retention.register(self.artifact_id, {'retention_days':1, 'reason':'Update', **changes}, 'steward')

    def test_intent_failure_prevents_file_deletion(self):
        self.retention.store.fail_on = self.retention.store.writes + 1
        with self.assertRaises(RuntimeError): self.retention.purge(self.artifact_id, 'steward', 'Expired')
        self.artifacts.resolve(self.artifact_id)
        self.assertEqual(self.retention.store.get('policy:'+self.artifact_id)['status'], 'active')

    def test_terminal_write_failure_is_recoverable_after_file_deletion(self):
        self.retention.store.fail_on = self.retention.store.writes + 2
        with self.assertRaises(RuntimeError): self.retention.purge(self.artifact_id, 'steward', 'Expired')
        self.assertEqual(self.retention.store.get('policy:'+self.artifact_id)['status'], 'purging')
        with self.assertRaises(ValueError): self.artifacts.resolve(self.artifact_id)
        with self.assertRaises(ValueError):
            self.retention.register(self.artifact_id, {'retention_days':10, 'reason':'Reactivate'}, 'other')
        result = self.retention.purge(self.artifact_id, 'recovery-steward', 'Retry')
        self.assertEqual(result['status'], 'purged')
        self.assertEqual(result['purged_by'], 'steward')
        self.assertEqual(result['purge_reason'], 'Expired')
        self.assertEqual(self.retention.purge(self.artifact_id, 'other', 'Retry'), result)

    def test_both_mutations_use_the_same_lock(self):
        self.retention.store.busy = True
        with self.assertRaises(ValueError): self.retention.purge(self.artifact_id, 'steward', 'Expired')
        with self.assertRaises(ValueError): self.retention.register(self.artifact_id, {'retention_days':1, 'reason':'Update'}, 'steward')
        self.assertEqual(set(self.retention.store.locks), {'policy:'+self.artifact_id})
        self.artifacts.resolve(self.artifact_id)

    def test_updated_legal_hold_prevents_purge(self):
        self.retention.register(self.artifact_id, {'retention_days':1, 'legal_hold':True, 'reason':'Hold'}, 'steward')
        self.retention._now = lambda: datetime.now(timezone.utc) + timedelta(days=4)
        with self.assertRaises(ValueError): self.retention.purge(self.artifact_id, 'steward', 'Expired')
        self.artifacts.resolve(self.artifact_id)
