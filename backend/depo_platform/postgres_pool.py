"""Small synchronous control-plane pool; no automatic replay of database writes."""
import atexit
from contextlib import contextmanager
import os
from queue import LifoQueue, Empty
import threading
import time

_groups = {}
_guard = threading.Lock()


class _Pool:
    def __init__(self, capacity):
        self.idle = LifoQueue(capacity)
        self.slots = threading.BoundedSemaphore(capacity)


@contextmanager
def connection(dsn, **options):
    import psycopg
    from psycopg.pq import TransactionStatus
    capacity = int(os.getenv('DEPO_POSTGRES_POOL_SIZE', '8'))
    if not 1 <= capacity <= 32: raise ValueError('DEPO_POSTGRES_POOL_SIZE must be 1-32 per service process')
    key = (dsn, tuple(sorted(options.items())), capacity)
    with _guard:
        pool = _groups.setdefault(key, _Pool(capacity))
    if not pool.slots.acquire(timeout=10): raise RuntimeError('PostgreSQL connection pool is busy; retry')
    database = None
    reusable = False
    try:
        while True:
            try: candidate, retained_at = pool.idle.get_nowait()
            except Empty: break
            if candidate.closed or time.monotonic() - retained_at > 60:
                candidate.close()
                continue
            database = candidate
            break
        if database is None: database = psycopg.connect(dsn, **options)
        yield database
        # Session locks use dedicated connections. Non-idle transactions are
        # discarded instead of leaking state or replaying failed operations.
        reusable = not database.closed and database.info.transaction_status == TransactionStatus.IDLE
    finally:
        try:
            if database is not None:
                if reusable: pool.idle.put_nowait((database, time.monotonic()))
                else: database.close()
        finally: pool.slots.release()


def close_idle():
    with _guard: pools = list(_groups.values())
    for pool in pools:
        while True:
            try: database, _ = pool.idle.get_nowait()
            except Empty: break
            database.close()


atexit.register(close_idle)
