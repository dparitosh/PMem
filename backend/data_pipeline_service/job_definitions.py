"""Durable, versioned definitions for the small governed Spark job surface.

Definitions deliberately describe only transformations this service implements.
They are not arbitrary Spark/Python execution documents: that would turn the
control plane into a remote-code-execution endpoint.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.mesh_store import PostgresRegistry
from .handlers import registry as handler_registry


store = PostgresRegistry("data_job_definitions")
_ID = re.compile(r"[a-z][a-z0-9-]{2,62}$")
_SEMVER = re.compile(r"\d+\.\d+\.\d+$")
JOB_CONTRACTS = handler_registry.contracts()
SUPPORTED_JOB_TYPES = set(JOB_CONTRACTS)
SUPPORTED_QUALITY_PROFILES = {"semantic-core-v1", "unstructured-evidence-v1", "data-quality-core-v1", "schema-analytics-v1"}
REQUIRED_QUALITY_PROFILES = {
    "data-quality-assessment": "data-quality-core-v1",
    "schema-analytics-product": "schema-analytics-v1",
}


def _schedule_errors(schedule: Any) -> list[str]:
    if schedule is None:
        return []
    if not isinstance(schedule, dict):
        return ["schedule must be an object"]
    interval = schedule.get("interval_seconds")
    replay_run_id = str(schedule.get("replay_run_id") or "").strip()
    errors = []
    if not isinstance(interval, int) or interval < 60 or interval > 86_400:
        errors.append("schedule.interval_seconds must be an integer between 60 and 86400")
    if not replay_run_id:
        errors.append("schedule.replay_run_id is required; scheduled jobs replay a retained immutable input")
    return errors


def _retry_errors(policy: Any) -> list[str]:
    if policy is None:
        return []
    if not isinstance(policy, dict):
        return ["retry_policy must be an object"]
    attempts, backoff = policy.get("max_attempts"), policy.get("backoff_seconds")
    errors = []
    if not isinstance(attempts, int) or not 1 <= attempts <= 5:
        errors.append("retry_policy.max_attempts must be an integer between 1 and 5")
    if not isinstance(backoff, int) or not 1 <= backoff <= 3600:
        errors.append("retry_policy.backoff_seconds must be an integer between 1 and 3600")
    return errors


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def key(job_id: str, version: str) -> str:
    return f"{job_id}:{version}"


def validate_definition(payload: dict[str, Any]) -> list[str]:
    required = ("job_id", "name", "version", "owner", "job_type", "quality_profile")
    errors = [f"{field} is required" for field in required if not str(payload.get(field) or "").strip()]
    job_id = str(payload.get("job_id") or "")
    if job_id and not _ID.fullmatch(job_id):
        errors.append("job_id must be lowercase kebab-case and 3–63 characters")
    version = str(payload.get("version") or "")
    if version and not _SEMVER.fullmatch(version):
        errors.append("version must be semantic version major.minor.patch")
    if payload.get("job_type") not in handler_registry.contracts():
        errors.append(f"job_type must be one of: {', '.join(sorted(handler_registry.contracts()))}")
    if payload.get("quality_profile") not in SUPPORTED_QUALITY_PROFILES:
        errors.append(f"quality_profile must be one of: {', '.join(sorted(SUPPORTED_QUALITY_PROFILES))}")
    required_profile = REQUIRED_QUALITY_PROFILES.get(payload.get("job_type"))
    if required_profile and payload.get("quality_profile") != required_profile:
        errors.append(f"job_type {payload.get('job_type')} requires quality_profile {required_profile}")
    if "enabled" in payload and not isinstance(payload["enabled"], bool):
        errors.append("enabled must be a boolean")
    if payload.get("schedule") is not None:
        errors.append("schedule is configured after the first retained run through the schedule endpoint")
    errors.extend(_retry_errors(payload.get("retry_policy")))
    standards = payload.get("allowed_standards", [])
    if payload.get("job_type") in {"normalize-ceim", "validate-semantic-batch", "normalize-unstructured-ceim"}:
        if not isinstance(standards, list) or not standards or any(not isinstance(item, str) or not item.strip() for item in standards):
            errors.append("allowed_standards must be a non-empty list for CEIM jobs")
    return errors


def create(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_definition(payload)
    if errors:
        raise ValueError("; ".join(errors))
    input_contract, output_contract = handler_registry.contracts()[payload["job_type"]]
    record = {
        "job_id": payload["job_id"],
        "name": payload["name"],
        "version": payload["version"],
        "owner": payload["owner"],
        "job_type": payload["job_type"],
        "quality_profile": payload["quality_profile"],
        "enabled": bool(payload.get("enabled", True)),
        "lifecycle_state": "draft",
        "allowed_standards": sorted({item.strip().lower() for item in payload.get("allowed_standards", [])}),
        "input_contract": input_contract,
        "output_contract": output_contract,
        "schedule": None,
        "retry_policy": dict(payload.get("retry_policy") or {"max_attempts": 1, "backoff_seconds": 30}),
        "created_at": now(),
        "approved_at": None,
        "approved_by": None,
    }
    existing = store.get(key(record["job_id"], record["version"]))
    if existing:
        raise FileExistsError("A job definition with this job_id and version already exists")
    return store.put(key(record["job_id"], record["version"]), record)


def all_definitions() -> list[dict[str, Any]]:
    return sorted(store.all().values(), key=lambda item: (item["job_id"], item["version"]), reverse=False)


def get(job_id: str, version: str) -> dict[str, Any] | None:
    return store.get(key(job_id, version))


def approve(job_id: str, version: str, approved_by: str) -> dict[str, Any]:
    record = get(job_id, version)
    if not record:
        raise LookupError("Data job definition was not found")
    if record["lifecycle_state"] == "disabled":
        raise ValueError("A disabled job version cannot be approved")
    approved = {**record, "lifecycle_state": "approved", "approved_at": now(), "approved_by": approved_by}
    return store.put(key(job_id, version), approved)


def disable(job_id: str, version: str, disabled_by: str) -> dict[str, Any]:
    record = get(job_id, version)
    if not record:
        raise LookupError("Data job definition was not found")
    disabled = {**record, "enabled": False, "lifecycle_state": "disabled", "disabled_at": now(), "disabled_by": disabled_by}
    return store.put(key(job_id, version), disabled)


def configure_schedule(job_id: str, version: str, payload: dict[str, Any], configured_by: str) -> dict[str, Any]:
    record = get(job_id, version)
    if not record:
        raise LookupError("Data job definition was not found")
    if record.get("lifecycle_state") != "approved" or not record.get("enabled"):
        raise ValueError("Only an approved, enabled job can be scheduled")
    schedule = {"interval_seconds": payload.get("interval_seconds"), "replay_run_id": payload.get("replay_run_id")}
    errors = _schedule_errors(schedule) + _retry_errors(payload.get("retry_policy"))
    if errors:
        raise ValueError("; ".join(errors))
    updated = {
        **record,
        "schedule": {**schedule, "configured_at": now(), "configured_by": configured_by},
        "retry_policy": dict(payload.get("retry_policy") or record.get("retry_policy") or {"max_attempts": 1, "backoff_seconds": 30}),
    }
    return store.put(key(job_id, version), updated)


def clear_schedule(job_id: str, version: str, configured_by: str) -> dict[str, Any]:
    record = get(job_id, version)
    if not record:
        raise LookupError("Data job definition was not found")
    return store.put(key(job_id, version), {**record, "schedule": None, "schedule_cleared_at": now(), "schedule_cleared_by": configured_by})
