"""Keep graph publication activity observable across service processes."""
import os
import threading
from contextlib import contextmanager
from functools import wraps

_guard = threading.Lock()
_locks = {}


@contextmanager
def publication_lock(ontology_id):
    if os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL'):
        from backend.mesh_store import PostgresRegistry
        with PostgresRegistry('graph_publication_activity').advisory_lock(str(ontology_id)) as acquired:
            yield acquired
        return
    with _guard:
        lock, users = _locks.get(ontology_id, (threading.Lock(), 0))
        _locks[ontology_id] = (lock, users + 1)
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired: lock.release()
        with _guard:
            _, users = _locks[ontology_id]
            if users == 1: del _locks[ontology_id]
            else: _locks[ontology_id] = (lock, users - 1)


def graph_publication(fn):
    @wraps(fn)
    def guarded(self, *, ontology_id, **kwargs):
        with publication_lock(ontology_id) as acquired:
            if not acquired:
                raise ValueError('A graph publication is already active for this ontology; verify before retrying.')
            return fn(self, ontology_id=ontology_id, **kwargs)
    return guarded
