"""Cross-process exclusion between ontology persistence and full cleanup."""
import os
import inspect
import threading
from contextlib import contextmanager
from functools import wraps

_local = threading.RLock()


class OntologyMaintenanceBusy(ValueError):
    pass


@contextmanager
def ontology_operation(*, cleanup=False):
    if os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL'):
        from backend.mesh_store import PostgresRegistry
        # Shared writers may call other services holding the same shared lock.
        # Cleanup requires exclusive access and fails immediately if any writer is active.
        suffix = '' if cleanup else '_shared'
        with PostgresRegistry('maintenance_state')._connect() as db, db.cursor() as cursor:
            cursor.execute(f'SELECT pg_try_advisory_lock{suffix}(hashtextextended(%s, 0))', ('depo:ontology-maintenance',))
            if not cursor.fetchone()[0]:
                raise OntologyMaintenanceBusy('Ontology maintenance or publication is active. Wait for it to finish, then retry.')
            try:
                yield
            finally:
                cursor.execute(f'SELECT pg_advisory_unlock{suffix}(hashtextextended(%s, 0))', ('depo:ontology-maintenance',))
    else:
        if not _local.acquire(blocking=False):
            raise OntologyMaintenanceBusy('Ontology maintenance or publication is active. Retry after completion.')
        try:
            yield
        finally:
            _local.release()


def ontology_writer(fn):
    if inspect.iscoroutinefunction(fn):
        @wraps(fn)
        async def guarded_async(*args, **kwargs):
            with ontology_operation():
                return await fn(*args, **kwargs)
        return guarded_async
    @wraps(fn)
    def guarded(*args, **kwargs):
        with ontology_operation():
            return fn(*args, **kwargs)
    return guarded


def ontology_cleanup(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        try:
            with ontology_operation(cleanup=True):
                return fn(*args, **kwargs)
        except OntologyMaintenanceBusy as exc:
            from fastapi import HTTPException
            raise HTTPException(409, str(exc)) from exc
    return guarded
