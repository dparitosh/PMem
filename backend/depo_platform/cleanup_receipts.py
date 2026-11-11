"""Cross-store cleanup progress; never automatically replay a graph reset."""
from datetime import datetime, timezone
from uuid import uuid4


class CleanupReceipt:
    def __init__(self, store):
        self.store = store
        self.record = {'run_id': 'cleanup-' + uuid4().hex, 'operation': 'clean-schema',
                       'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'running',
                       'phases': {key: 'pending' for key in ('graph', 'reconciliation', 'ontology_metadata', 'import_workflows')},
                       'automatic_replay_allowed': False, 'receipt_persisted': True}
        self.persist(required=True)

    def persist(self, *, required=False):
        try:
            self.store.put(self.record['run_id'], self.record)
        except Exception:
            self.record['receipt_persisted'] = False
            if required:
                raise RuntimeError('Cleanup receipt unavailable; no graph reset was started') from None

    def phase(self, name, status, *, required=False):
        self.record['phases'][name] = status
        self.persist(required=required)

    def finish(self):
        self.record['status'] = 'completed' if self.record['receipt_persisted'] and all(
            status == 'completed' for status in self.record['phases'].values()) else 'partial'
        self.record['finished_at'] = datetime.now(timezone.utc).isoformat()
        self.persist()
        if not self.record['receipt_persisted']:
            self.record['status'] = 'partial'
        return self.record
