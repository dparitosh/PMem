"""Leased execution core; independent of HTTP routers and scheduler wiring."""
from datetime import datetime, timezone
from typing import Any
from backend.depo_platform.execution_guard import guarded_execution, ensure_execution_allowed
from backend.depo_platform.operations import OperationContext, operation_scope, remaining_seconds, current_operation
from . import run_records
from .runner import runner
from .handlers import registry as handler_registry

def execute_claimed_job(definition: dict[str, Any], payload: dict[str, Any], run: dict[str, Any], lease_lost=None) -> dict[str, Any]:
    """Execute a PostgreSQL-leased run without creating a duplicate manifest."""
    if definition["job_type"] in {"normalize-ceim", "validate-semantic-batch", "normalize-unstructured-ceim"}:
        standard = str(payload.get("standard") or "").strip().lower()
        if standard not in definition.get("allowed_standards", []):
            raise ValueError("The request standard is not allowed by this data-job definition")
    context = execution_context(run)
    def check_lease():
        remaining_seconds(context.deadline_at)
        if lease_lost is not None and lease_lost.is_set():
            raise RuntimeError("Worker lease renewal failed; execution persistence is fenced")
        current = run_records.get(run['run_id'])
        if (not current or current.get('status') != 'running' or current.get('worker_id') != run.get('worker_id') or
                current.get('attempt') != run.get('attempt') or
                datetime.fromisoformat(current['lease']['expires_at']) <= datetime.now(timezone.utc)):
            raise RuntimeError("Worker no longer owns a live execution lease")
    with operation_scope(context), runner.execution_scope(context, lease_lost), guarded_execution(check_lease):
        result = handler_registry.get(definition["job_type"]).execute(runner, payload, correlation_id=run.get("correlation_id", ""))
        ensure_execution_allowed()
        persisted = run_records.complete(run, result)
    from .analytics_evidence import run_result
    return run_result(result, persisted)


def execution_context(run):
    deadline = run_records.execution_deadline(run)
    inherited = current_operation()
    if inherited and datetime.fromisoformat(inherited.deadline_at) < datetime.fromisoformat(deadline):
        deadline = inherited.deadline_at
    return OperationContext(run['run_id'], deadline)


def execute_immediate_job(definition, payload, run):
    """The synchronous API shares the worker's absolute deadline and Spark cancellation."""
    context = execution_context(run)
    with operation_scope(context), runner.execution_scope(context), guarded_execution(lambda: remaining_seconds(context.deadline_at)):
        result = handler_registry.get(definition['job_type']).execute(runner, payload, correlation_id=run.get('correlation_id', ''))
        ensure_execution_allowed()
        persisted = run_records.complete(run, result)
    return result, persisted
