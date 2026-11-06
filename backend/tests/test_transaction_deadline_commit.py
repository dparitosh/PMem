"""Deadlines and lease fences cover commit; expired cleanup never sends SQL."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
import sys

import pytest

from backend.depo_platform.postgres_pool import _DeadlineConnection, _DeadlineCursor, connection, close_idle
from backend.depo_platform.operations import operation_scope
from backend.depo_platform.execution_guard import guarded_execution


class Budget:
    def __init__(self, seconds=3):
        self.seconds = seconds

    def timeout(self, requested):
        if self.seconds <= 0:
            raise TimeoutError('operation deadline exceeded')
        return min(requested, self.seconds)


class Database:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.calls = []
        self.info = SimpleNamespace(transaction_status='idle')

    @contextmanager
    def transaction(self, **kwargs):
        try:
            yield self
        except BaseException:
            self.rollbacks += 1
            raise
        else:
            self.commits += 1

    @contextmanager
    def cursor(self):
        yield SimpleNamespace(execute=lambda *args: self.calls.append(args))

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def test_expiry_between_last_statement_and_commit_rolls_back():
    raw = Database()
    budget = Budget()
    with operation_scope(budget), pytest.raises(TimeoutError):
        with _DeadlineConnection(raw).transaction():
            budget.seconds = 0
    assert raw.commits == 0
    assert raw.rollbacks == 1
    assert raw.calls == []


def test_lease_lost_before_commit_rolls_back():
    raw = Database()
    lost = [False]
    def fence():
        if lost[0]:
            raise RuntimeError('lease lost')
    with operation_scope(Budget()), guarded_execution(fence), pytest.raises(RuntimeError, match='lease lost'):
        with _DeadlineConnection(raw).transaction():
            lost[0] = True
    assert raw.commits == 0
    assert raw.rollbacks == 1


def test_commit_uses_remaining_budget_and_rechecks_after_configuration():
    raw = Database()
    budget = Budget()
    with operation_scope(budget):
        with _DeadlineConnection(raw).transaction():
            budget.seconds = .25
    assert raw.commits == 1
    assert raw.calls[-1][1] == ('250', '250')
    raw = Database()
    @contextmanager
    def cursor():
        def configure(*args):
            budget.seconds = 0
        yield SimpleNamespace(execute=configure)
    raw.cursor = cursor
    budget.seconds = 1
    with operation_scope(budget), pytest.raises(TimeoutError):
        _DeadlineConnection(raw).commit()
    assert raw.commits == 0


def test_pool_discards_expired_connection_without_cleanup_sql():
    raw = Database()
    budget = Budget()
    modules = {'psycopg': SimpleNamespace(connect=lambda *args, **kwargs: raw),
               'psycopg.pq': SimpleNamespace(TransactionStatus=SimpleNamespace(IDLE='idle'))}
    with patch.dict(sys.modules, modules), operation_scope(budget):
        with connection('expired-cleanup-regression', autocommit=True):
            budget.seconds = 0
    assert raw.closed
    assert raw.calls == []
    close_idle()


def test_pool_preserves_commit_fence_when_only_a_lease_guard_is_present():
    raw = Database()
    lost = [False]
    def fence():
        if lost[0]:
            raise RuntimeError('lease lost')
    modules = {'psycopg': SimpleNamespace(connect=lambda *args, **kwargs: raw),
               'psycopg.pq': SimpleNamespace(TransactionStatus=SimpleNamespace(IDLE='idle'))}
    with patch.dict(sys.modules, modules), guarded_execution(fence), pytest.raises(RuntimeError, match='lease lost'):
        with connection('lease-only-commit-regression', autocommit=True) as db:
            with db.transaction():
                lost[0] = True
    assert raw.commits == 0
    assert raw.rollbacks == 1
    assert raw.closed


def test_cleanup_expiring_during_timeout_configuration_does_not_dispatch_reset():
    budget = Budget()
    calls = []
    def execute(*args):
        calls.append(args)
        budget.seconds = 0
    raw = SimpleNamespace(execute=execute)
    with operation_scope(budget), pytest.raises(TimeoutError):
        _DeadlineCursor(raw).execute('RESET ALL')
    assert len(calls) == 1
    assert 'set_config' in calls[0][0]
