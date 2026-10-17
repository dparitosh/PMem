"""Cross-process publication barrier for application graph sessions.

Shared transaction locks let existing sessions finish before activation. A
durable marker keeps partial replacements unavailable after a worker crash.
Only the same publication can resume and clear that marker.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import os
import sys
import time
from functools import wraps
from uuid import uuid4

_inside = ContextVar('graph_projection_access', default=False)
_NAMESPACE = 'graph_projection_visibility_v1'
_KEY = 'activation'
_LOCK = _NAMESPACE + ':barrier'


def _store():
    from backend.mesh_store import PostgresRegistry
    return PostgresRegistry(_NAMESPACE)


def _configured():
    return bool(os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL'))


@contextmanager
def projection_access():
    if _inside.get() or not _configured():
        yield
        return
    store = _store()
    from backend.depo_platform.postgres_pool import pool_scope
    with pool_scope('graph-projection'), store._connect() as db, db.transaction(), db.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_xact_lock_shared(hashtextextended(%s, 0))', (_LOCK,))
        if not cursor.fetchone()[0]:
            raise RuntimeError('Graph publication activation is in progress; retry graph access shortly')
        cursor.execute('SELECT value FROM depo_registry WHERE namespace=%s AND key=%s', (_NAMESPACE, _KEY))
        row = cursor.fetchone()
        if row and row[0]:
            raise RuntimeError('Graph publication activation requires completion; resume the retained publication job')
        token = _inside.set(True)
        try:
            yield
        finally:
            _inside.reset(token)


@contextmanager
def _deadline_scope(deadline, *, recovery=False):
    from datetime import datetime, timedelta, timezone
    from backend.depo_platform.operations import OperationContext, current_operation, operation_scope
    from backend.depo_platform.execution_guard import guarded_execution
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Graph activation deadline exceeded')
    inherited = current_operation()
    if inherited and not recovery:
        remaining = inherited.timeout(remaining)
    context = OperationContext('graph-barrier-recovery' if recovery else 'graph-activation',
        (datetime.now(timezone.utc) + timedelta(seconds=remaining)).isoformat())
    with operation_scope(context):
        # Recovery only changes an owned control-plane marker, never graph data.
        if recovery:
            with guarded_execution(lambda: None):
                yield
        else:
            yield


def _same_publication(marker, ontology_id, publication_id):
    return bool(marker and marker.get('ontology_id') == ontology_id
                and marker.get('publication_id') == publication_id)


def _clear_marker(store, marker, *, recovery=False):
    # A small, explicit recovery allowance is needed after a deadline. The CAS
    # cannot clear another publication or an uncertain activation phase.
    with _deadline_scope(time.monotonic() + 3, recovery=recovery):
        return store.compare_and_put(_KEY, marker, {})


class _Activation:
    def __init__(self, store, marker):
        self.store = store
        self.marker = marker

    def begin_mutation(self):
        # Recheck ownership before every batch, including resumed activations.
        updated = {**self.marker, 'phase': 'activating'}
        if not self.store.compare_and_put(_KEY, self.marker, updated):
            raise RuntimeError('Graph activation ownership changed; verify the retained publication')
        self.marker = updated

    @property
    def owner_id(self):
        return self.marker['owner_id']


@contextmanager
def replacement_access(ontology_id, publication_id, *, timeout=60, deadline=None):
    # Establish the deadline before connections, marker writes and lock waits.
    deadline = time.monotonic() + timeout if deadline is None else deadline
    if not _configured():
        raise RuntimeError('PostgreSQL persistence is required for bounded graph publication activation')
    if _inside.get():
        raise RuntimeError('Cannot activate a publication inside a graph reader session')
    store = _store()
    with _deadline_scope(deadline), store.advisory_lock('activation-writer', bounded=True) as writer:
        if not writer:
            raise RuntimeError('Another graph publication is activating; retry the retained job')
        prior = store.get(_KEY)
        if prior and not _same_publication(prior, ontology_id, publication_id):
            raise RuntimeError('Complete the interrupted graph publication before activating another ontology')
        # Old markers without a phase are uncertain and must remain protected.
        marker = {**(prior or {'ontology_id': ontology_id, 'publication_id': publication_id, 'phase': 'draining'}),
                  'owner_id': uuid4().hex}
        activation = _Activation(store, marker)
        try:
            if prior is None:
                store.create(_KEY, marker)
            elif not store.compare_and_put(_KEY, prior, marker):
                raise RuntimeError('Graph activation ownership changed before reader drain')
            with store._session_connect(bounded=True) as db, db.cursor() as cursor:
                while True:
                    from backend.depo_platform.operations import current_operation
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Graph sessions did not drain before the activation deadline')
                    current_operation().timeout(remaining)
                    cursor.execute('SELECT pg_try_advisory_lock(hashtextextended(%s, 0))', (_LOCK,))
                    if cursor.fetchone()[0]:
                        break
                    time.sleep(min(.05, remaining))
                token = _inside.set(True)
                try:
                    yield activation
                    # Caller has committed the exact graph publication receipt.
                    _clear_marker(store, activation.marker, recovery=True)
                finally:
                    _inside.reset(token)
                # The dedicated session closes here and releases its lock,
                # even when the deadline prevents another SQL command.
        except BaseException:
            if activation.marker.get('phase') == 'draining':
                try:
                    _clear_marker(store, activation.marker, recovery=True)
                except Exception:
                    # Preserve the original error. A later idle receipt poll
                    # can clear this marker, which proves no mutation started.
                    pass
            raise


def reconcile_activation(ontology_id, publication_id, receipt=None):
    """Repair an idle publication barrier using a matching committed receipt.

    Caller holds the per-ontology publication lock, so proof cannot race another
    writer of this ontology. An unfinished activation is never cleared by age.
    """
    if not _configured():
        return
    store = _store()
    with _deadline_scope(time.monotonic() + 3), store.advisory_lock('activation-writer', bounded=True) as writer:
        if not writer:
            return
        marker = store.get(_KEY)
        if not _same_publication(marker, ontology_id, publication_id):
            return
        published = (isinstance(receipt, dict) and receipt.get('ontology_id') == ontology_id
                     and receipt.get('publication_id') == publication_id
                     and receipt.get('status') == 'published' and receipt.get('current') is True
                     and all(type(receipt.get(key)) is int and receipt[key] >= 0
                             for key in ('resources', 'relationships', 'hierarchy_edges')))
        if marker.get('phase') == 'draining' or published:
            _clear_marker(store, marker)


class _Session:
    def __init__(self, session):
        self._session = session
        self._value = session
        self._access = None

    def __enter__(self):
        if self._access is not None:
            return self
        self._access = projection_access()
        try:
            self._access.__enter__()
        except BaseException:
            self._access = None
            self._session.close()
            raise
        try:
            self._value = self._session.__enter__()
            return self
        except BaseException:
            self._access.__exit__(*sys.exc_info())
            self._access = None
            raise

    def __exit__(self, *args):
        if self._access is None:
            return
        try:
            return self._session.__exit__(*args)
        finally:
            self._access.__exit__(*args)
            self._access = None

    def close(self):
        if self._access is not None:
            self.__exit__(None, None, None)
        else:
            self._session.close()

    def __getattr__(self, name):
        if name in {'run', 'execute_read', 'execute_write', 'begin_transaction'} and self._access is None:
            self.__enter__()
        return getattr(self._value, name)


class _Driver:
    def __init__(self, driver):
        self._driver = driver

    def __enter__(self):
        self._driver.__enter__()
        return self

    def __exit__(self, *args):
        return self._driver.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._driver, name)

    def session(self, *args, **kwargs):
        return _Session(self._driver.session(*args, **kwargs))

    def execute_query(self, *args, **kwargs):
        with projection_access():
            return self._driver.execute_query(*args, **kwargs)


def guard_driver(driver):
    return driver if isinstance(driver, _Driver) else _Driver(driver)


class GraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        from neo4j import GraphDatabase as NativeGraphDatabase
        return guard_driver(NativeGraphDatabase.driver(*args, **kwargs))


def graph_operation(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with projection_access():
            return function(*args, **kwargs)
    return guarded
