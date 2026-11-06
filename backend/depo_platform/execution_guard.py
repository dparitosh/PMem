"""Cooperative persistence fences for leased job execution."""
from contextlib import contextmanager
from contextvars import ContextVar
_guard = ContextVar('depo_execution_guard', default=None)
_checking = ContextVar('depo_execution_guard_checking', default=False)


def has_execution_guard():
    return _guard.get() is not None


def is_execution_check():
    return _checking.get()


def ensure_execution_allowed():
    guard = _guard.get()
    if guard is None or _checking.get():
        return
    # Lease validation itself reads the control plane. Suppress only recursive
    # validation, not the guard on the next business statement or commit.
    token = _checking.set(True)
    try:
        guard()
    finally:
        _checking.reset(token)


@contextmanager
def guarded_execution(guard):
    token = _guard.set(guard)
    try:
        ensure_execution_allowed()
        yield
    finally:
        _guard.reset(token)
