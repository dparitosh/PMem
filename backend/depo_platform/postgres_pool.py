"""Small synchronous control-plane pool; no automatic replay of database writes."""
from contextvars import ContextVar
import atexit
from contextlib import contextmanager
import os
from queue import LifoQueue, Empty
import threading
import time

_role = ContextVar('depo_postgres_pool_role', default='registry')


class PoolBusy(RuntimeError):
    """Transient capacity exhaustion; never an invitation to replay a write."""


@contextmanager
def pool_scope(role):
    token = _role.set(role)
    try:
        yield
    finally:
        _role.reset(token)


_groups = {}
_guard = threading.Lock()


class _Pool:
    def __init__(self, capacity):
        self.idle = LifoQueue(capacity)
        self.slots = threading.BoundedSemaphore(capacity)
        self.capacity = capacity
        self.wait_seconds = 0.0
        self.busy_count = 0


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
        requested = float(os.getenv('DEPO_REGISTRY_STATEMENT_TIMEOUT_SECONDS', '30'))
        seconds = operation.timeout(requested) if operation else requested
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
        if not isolation:
            # Configuring the server timeout is a network round trip too.
            # Do not dispatch work if the deadline or lease changed meanwhile.
            self._budget(configure=False)
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

    def _before_commit(self):
        # Transaction.__exit__ and explicit commit otherwise bypass cursor
        # fences. Raising inside the transaction causes its normal rollback.
        with self.database.cursor() as cursor:
            checked = _DeadlineCursor(cursor)
            checked._budget()
            checked._budget(configure=False)

    @contextmanager
    def transaction(self, *args, **kwargs):
        with self.database.cursor() as cursor:
            _DeadlineCursor(cursor)._budget(configure=False)
        with self.database.transaction(*args, **kwargs) as transaction:
            yield transaction
            if not kwargs.get('force_rollback', False):
                self._before_commit()

    def commit(self):
        self._before_commit()
        return self.database.commit()


@contextmanager
def connection(dsn, **options):
    import psycopg
    from psycopg.pq import TransactionStatus
    from .operations import current_operation
    from .execution_guard import has_execution_guard, is_execution_check
    operation = current_operation()
    role = 'lease-validation' if is_execution_check() else _role.get()
    setting = {'graph-projection':'DEPO_POSTGRES_GRAPH_POOL_SIZE', 'lease-validation':'DEPO_POSTGRES_LEASE_POOL_SIZE'}.get(role, 'DEPO_POSTGRES_POOL_SIZE')
    capacity = int(os.getenv(setting, '8' if role == 'registry' else '4'))
    if not 1 <= capacity <= 32: raise ValueError('DEPO_POSTGRES_POOL_SIZE must be 1-32 per service process')
    key = (dsn, tuple(sorted(options.items())), capacity, role)
    with _guard:
        pool = _groups.setdefault(key, _Pool(capacity))
    started = time.monotonic()
    acquired = pool.slots.acquire(timeout=operation.timeout(10) if operation else 10)
    with _guard:
        pool.wait_seconds += time.monotonic() - started
        if not acquired:
            pool.busy_count += 1
    if not acquired:
        raise PoolBusy('PostgreSQL connection pool is busy; retry')
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
        yield _DeadlineConnection(database) if operation or has_execution_guard() else database
        # Session locks use dedicated connections. Non-idle transactions are
        # discarded instead of leaking state or replaying failed operations.
        reusable = not database.closed and database.info.transaction_status == TransactionStatus.IDLE
        if reusable and (operation is not None or has_execution_guard()):
            # One bounded reset restores session defaults. If the operation or
            # lease has expired, discard the connection without cleanup SQL.
            try:
                with database.cursor() as cursor:
                    _DeadlineCursor(cursor).execute('RESET ALL')
                reusable = database.info.transaction_status == TransactionStatus.IDLE
            except Exception:
                reusable = False
    finally:
        try:
            if database is not None:
                if reusable: pool.idle.put_nowait((database, time.monotonic()))
                else: database.close()
        finally: pool.slots.release()


def pool_metrics():
    # Never export DSNs, credentials or connection-option keys.
    with _guard:
        return [{'role':key[-1], 'capacity':pool.capacity, 'idle':pool.idle.qsize(),
                 'wait_seconds':pool.wait_seconds, 'busy_count':pool.busy_count}
                for key,pool in _groups.items()]


def close_idle():
    with _guard: pools = list(_groups.values())
    for pool in pools:
        while True:
            try: database, _ = pool.idle.get_nowait()
            except Empty: break
            database.close()


atexit.register(close_idle)
