"""Cooperative persistence fences for leased job execution."""
from contextlib import contextmanager
from contextvars import ContextVar
_guard = ContextVar('depo_execution_guard', default=None)

def ensure_execution_allowed():
    guard = _guard.get()
    if guard is not None: guard()

@contextmanager
def guarded_execution(guard):
    token = _guard.set(guard)
    try:
        guard()
        yield
    finally: _guard.reset(token)
