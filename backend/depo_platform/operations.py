"""Transport-independent operation deadlines and safe progress metadata."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

_current = ContextVar('depo_operation', default=None)


def remaining_seconds(deadline_at):
    deadline = datetime.fromisoformat(deadline_at)
    if deadline.tzinfo is None:
        raise ValueError('Operation deadline must include timezone')
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise TimeoutError('Operation deadline exceeded; verify retained outcome before retrying')
    return remaining


@dataclass(frozen=True)
class OperationContext:
    operation_id: str
    deadline_at: str
    on_progress: Callable | None = None

    def timeout(self, requested):
        return min(requested, remaining_seconds(self.deadline_at))


@contextmanager
def operation_scope(context):
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)


def current_operation():
    return _current.get()
