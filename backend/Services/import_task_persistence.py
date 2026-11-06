"""Atomic import snapshots with Windows sharing retries and process ownership."""
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile
import time

logger = logging.getLogger(__name__)


class TaskPersistenceError(RuntimeError):
    pass


def atomic_bytes(path, data):
    """Keep the old file until replacement succeeds; never delete to make room."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(7):
            try:
                os.replace(temporary, path)
                return
            except OSError as exc:
                transient = isinstance(exc, PermissionError) or getattr(exc, 'winerror', None) in {5, 32, 33}
                if not transient or attempt == 6:
                    raise
                time.sleep(min(.05 * 2 ** attempt, .5))
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning('Import snapshot temporary file could not be removed: %s', Path(temporary).name)


@contextmanager
def task_lock(path, timeout=5):
    """OS releases ownership on exit/crash; an old lock file is harmless."""
    with path.with_suffix('.lock').open('a+b') as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b'0')
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if time.monotonic() >= deadline:
                    raise TaskPersistenceError('Import task persistence is busy; refresh status before retrying') from exc
                time.sleep(.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def persist_task(path, task, build_snapshot):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with task_lock(path):
        # Build only after owning the lock; another thread may have committed.
        snapshot = build_snapshot(task)
        snapshot.pop('_persistence_error', None)
        version = int(snapshot.get('_persist_version', 0) or 0)
        if path.exists():
            previous = json.loads(path.read_text(encoding='utf-8'))
            if int(previous.get('_persist_version', 0) or 0) > version:
                raise TaskPersistenceError('A newer import snapshot exists; refresh task state before writing')
        snapshot['_persist_version'] = version + 1
        snapshot['_persisted_by'] = {'pid': os.getpid(), 'time': datetime.now(timezone.utc).isoformat(), 'version': version + 1}
        # Content-addressed sidecars keep the old snapshot consistent when the
        # final replace fails. Identical rows are reused on progress updates.
        for field, pointer in (('parsed_rows', '_parsed_rows_file'), ('shacl_report', '_shacl_file')):
            if field in snapshot:
                data = json.dumps(snapshot.pop(field), ensure_ascii=True, default=str).encode('utf-8')
                name = path.name + '.' + field + '.' + hashlib.sha256(data).hexdigest() + '.json'
                sidecar = path.with_name(name)
                if not sidecar.exists():
                    atomic_bytes(sidecar, data)
                snapshot[pointer] = name
        atomic_bytes(path, json.dumps(snapshot, ensure_ascii=True, default=str).encode('utf-8'))
        for key in ('_persist_version', '_persisted_by', '_parsed_rows_file', '_shacl_file'):
            if key in snapshot:
                task[key] = snapshot[key]
        task.pop('_persistence_error', None)
        return snapshot
