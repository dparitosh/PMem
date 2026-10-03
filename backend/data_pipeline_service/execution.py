"""Leased execution core; independent of HTTP routers and scheduler wiring."""
from datetime import datetime, timezone
from typing import Any
from backend.depo_platform.execution_guard import guarded_execution, ensure_execution_allowed
from . import run_records
from .runner import runner
from .handlers import registry as handler_registry

def execute_claimed_job(definition: dict[str, Any], payload: dict[str, Any], run: dict[str, Any], lease_lost=None) -> dict[str, Any]:
    """Execute a PostgreSQL-leased run without creating a duplicate manifest."""
    if definition["job_type"] in {"normalize-ceim", "validate-semantic-batch", "normalize-unstructured-ceim"}:
        standard = str(payload.get("standard") or "").strip().lower()
        if standard not in definition.get("allowed_standards", []):
            raise ValueError("The request standard is not allowed by this data-job definition")
    def check_lease():
        if lease_lost is not None and lease_lost.is_set():
            raise RuntimeError("Worker lease renewal failed; execution persistence is fenced")
        current = run_records.get(run['run_id'])
        if (not current or current.get('status') != 'running' or current.get('worker_id') != run.get('worker_id') or
                current.get('attempt') != run.get('attempt') or
                datetime.fromisoformat(current['lease']['expires_at']) <= datetime.now(timezone.utc)):
            raise RuntimeError("Worker no longer owns a live execution lease")
    with guarded_execution(check_lease):
        result = handler_registry.get(definition["job_type"]).execute(runner, payload, correlation_id=run.get("correlation_id", ""))
        ensure_execution_allowed()
        persisted = run_records.complete(run, result)
    return {**result, "run_manifest": persisted}
