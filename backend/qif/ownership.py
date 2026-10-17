"""Exclusive ownership for the local-file QIF queue, released on process exit."""
from contextlib import contextmanager
import os


@contextmanager
def queue_owner(root):
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / '.queue-owner.lock').open('a+b')
    locked = False
    try:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('QIF task storage already has an owner. Run one QIF process per task store.') from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError('QIF task storage already has an owner. Run one QIF process per task store.') from exc
        locked = True
        yield
    finally:
        if locked:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


from contextvars import ContextVar
_held_states = ContextVar('qif_state_locks', default=frozenset())
_execution_connection = ContextVar('qif_execution_connection', default=None)


def shared_storage():
    mode = os.getenv('QIF_TASK_STORAGE', 'local').strip().lower()
    if mode not in {'local', 'shared'}:
        raise RuntimeError('QIF_TASK_STORAGE must be local or shared')
    return mode == 'shared'


def task_root(default):
    from pathlib import Path
    configured = os.getenv('QIF_TASK_ROOT', '').strip()
    if shared_storage() and not configured:
        raise RuntimeError('Shared QIF storage requires QIF_TASK_ROOT on a shared persistent volume')
    if configured and not Path(configured).is_absolute():
        raise RuntimeError('QIF_TASK_ROOT must be absolute')
    return Path(configured) if configured else default


def _registry():
    from backend.mesh_store import PostgresRegistry
    # Stable namespace across hosts and differing mount paths.
    return PostgresRegistry('qif_shared_queue_v1')


@contextmanager
def state_lock(identity):
    if not shared_storage() or identity in _held_states.get():
        yield
        return
    from fastapi import HTTPException
    with _registry().advisory_lock('state:' + identity, bounded=True) as acquired:
        if not acquired:
            raise HTTPException(503, 'QIF task state is busy; refresh before retrying', headers={'Retry-After':'1'})
        token = _held_states.set(_held_states.get() | {identity})
        try:
            yield
        finally:
            _held_states.reset(token)


def ensure_owner():
    connection = _execution_connection.get()
    if connection is not None:
        # A lost session also loses its advisory lock. The old executor must
        # stop before subsequent stage transitions or write dispatch.
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')


@contextmanager
def execution_owner(identity, root=None):
    if not shared_storage():
        if root is None:
            raise RuntimeError("Local QIF execution ownership requires the task root")
        # Retained by the worker thread even while the HTTP service drains.
        manager = queue_owner(root / identity)
        try:
            manager.__enter__()
        except RuntimeError as exc:
            if "already has an owner" not in str(exc):
                raise
            yield False
            return
        try:
            yield True
        finally:
            manager.__exit__(None, None, None)
        return
    registry = _registry()
    with registry._session_connect(bounded=True) as connection, connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(hashtextextended(%s, 0))',
                       ('qif_shared_queue_v1:execution:' + identity,))
        acquired = bool(cursor.fetchone()[0])
        token = _execution_connection.set(connection if acquired else None)
        try:
            yield acquired
        finally:
            _execution_connection.reset(token)
            # Dedicated connection closure releases ownership, even after expiry.


@contextmanager
def service_owner(root):
    if shared_storage():
        verify_shared_storage(root)
        yield
    else:
        with queue_owner(root):
            yield



def verify_shared_storage(root):
    """All replicas must see the same retained volume, even at different mounts."""
    from uuid import uuid4
    from pathlib import Path
    artifact_root = os.getenv('ARTIFACT_STORAGE', '').strip()
    if not artifact_root or not Path(artifact_root).is_absolute():
        raise RuntimeError('Shared QIF storage requires absolute ARTIFACT_STORAGE on a shared persistent volume')
    registry = _registry()
    with registry.advisory_lock('storage-identity', bounded=True) as acquired:
        if not acquired:
            raise RuntimeError('Shared QIF storage validation is busy; retry startup')
        identities = {}
        for name, directory in (('tasks', root), ('artifacts', Path(artifact_root))):
            directory.mkdir(parents=True, exist_ok=True)
            marker = directory / '.qif-storage-id'
            if not marker.exists():
                with marker.open('x', encoding='ascii') as file:
                    file.write(uuid4().hex)
            identity = marker.read_text(encoding='ascii').strip()
            if len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
                raise RuntimeError('Invalid QIF shared storage identity; restore the retained volume marker')
            identities[name] = identity
        retained = registry.get('storage-identity')
        if retained is None:
            registry.create('storage-identity', identities)
        elif retained != identities:
            raise RuntimeError('QIF replicas do not share the registered task/artifact volumes. Correct the mounts; retain data and storage markers.')
