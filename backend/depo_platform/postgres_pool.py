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


class _DeadlineCursor:
    """Recalculate the remaining budget before every SQL dispatch."""
    def __init__(self, cursor):
        self.cursor = cursor
        self._bulk_rowcount = None
    @property
    def rowcount(self):
        return self.cursor.rowcount if self._bulk_rowcount is None else self._bulk_rowcount
    def __getattr__(self, name):
        return getattr(self.cursor, name)
    def __enter__(self):
        self.cursor.__enter__()
        return self
    def __exit__(self, *args):
        return self.cursor.__exit__(*args)
    def _budget(self, *, configure=True):
        from .operations import current_operation
        from .execution_guard import ensure_execution_allowed
        ensure_execution_allowed()
        operation = current_operation()
        seconds = operation.timeout(float(os.getenv('DEPO_REGISTRY_STATEMENT_TIMEOUT_SECONDS', '30')))
        if seconds < .001:
            raise TimeoutError('PostgreSQL operation deadline exceeded')
        if not configure:
            return
        self.cursor.execute("SELECT set_config('statement_timeout', %s, false), set_config('lock_timeout', %s, false)",
                            (str(int(seconds * 1000)), str(int(min(seconds, 10) * 1000))))
    def execute(self, *args, **kwargs):
        self._bulk_rowcount = None
        query = args[0] if args else kwargs.get('query')
        # PostgreSQL requires isolation selection before any query, including
        # the SELECT used to configure its statement budget.
        isolation = isinstance(query, str) and query.lstrip().upper().startswith('SET TRANSACTION ')
        self._budget(configure=False) if isolation else self._budget()
        self.cursor.execute(*args, **kwargs)
        return self
    def executemany(self, query, params, **kwargs):
        # A bulk driver pipeline otherwise gives every statement the initial
        # budget, even after the workflow deadline has elapsed.
        total = 0
        for values in params:
            self.execute(query, values, **kwargs)
            total += max(0, self.cursor.rowcount)
        self._bulk_rowcount = total
        return self


class _DeadlineConnection:
    def __init__(self, database):
        self.database = database
    def __getattr__(self, name):
        return getattr(self.database, name)
    def cursor(self, *args, **kwargs):
        return _DeadlineCursor(self.database.cursor(*args, **kwargs))
    def execute(self, *args, **kwargs):
        return self.cursor().execute(*args, **kwargs)


@contextmanager
def connection(dsn, **options):
    import psycopg
    from psycopg.pq import TransactionStatus
    from .operations import current_operation
    operation = current_operation()
    capacity = int(os.getenv('DEPO_POSTGRES_POOL_SIZE', '8'))
    if not 1 <= capacity <= 32: raise ValueError('DEPO_POSTGRES_POOL_SIZE must be 1-32 per service process')
    key = (dsn, tuple(sorted(options.items())), capacity)
    with _guard:
        pool = _groups.setdefault(key, _Pool(capacity))
    if not pool.slots.acquire(timeout=operation.timeout(10) if operation else 10): raise RuntimeError('PostgreSQL connection pool is busy; retry')
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
        if database is None:
            connect_options = dict(options)
            if operation:
                import math
                budget = operation.timeout(connect_options.get('connect_timeout', 10))
                # libpq enforces a minimum two-second connection timeout.
                if budget < 2:
                    raise TimeoutError('Insufficient operation budget to connect to PostgreSQL')
                connect_options['connect_timeout'] = max(2, math.floor(budget))
            database = psycopg.connect(dsn, **connect_options)
        if operation:
            operation.timeout(1)
        yield _DeadlineConnection(database) if operation else database
        # Session locks use dedicated connections. Non-idle transactions are
        # discarded instead of leaking state or replaying failed operations.
        reusable = not database.closed and database.info.transaction_status == TransactionStatus.IDLE
        if reusable and operation is not None:
            # Deadline settings are session scoped. Restore the connection's
            # configured defaults before another operation borrows it.
            try:
                database.execute('RESET statement_timeout')
                database.execute('RESET lock_timeout')
                reusable = database.info.transaction_status == TransactionStatus.IDLE
            except Exception:
                reusable = False
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
