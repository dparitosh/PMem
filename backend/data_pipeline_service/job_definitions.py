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
    "connector-ceim-normalize":"semantic-core-v1",
    "semantic-business-mart":"semantic-core-v1",
    "graph-source-snapshot":"semantic-core-v1",
    "semantic-source-review":"semantic-core-v1",
    "rdf-semantic-materialize":"semantic-core-v1",
    "semantic-dataset-analysis":"semantic-core-v1",
    "data-quality-assessment": "data-quality-core-v1",
    "schema-analytics-product": "schema-analytics-v1",
    "xml-analytics-materialize": "schema-analytics-v1",
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
    if payload.get("job_type") in {"normalize-ceim", "validate-semantic-batch", "normalize-unstructured-ceim", "connector-ceim-normalize"}:
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
    if isinstance(store, PostgresRegistry):
        from backend.depo_platform.resource_identity import identify
        identity=identify('WF','data-pipeline',record['job_id'],name=record['name'])
        record.update(workflow_uuid=identity['object_id'],workflow_number=identity['number'])
    return store.create(key(record["job_id"], record["version"]), record)


def all_definitions() -> list[dict[str, Any]]:
    return sorted(store.all().values(), key=lambda item: (item["job_id"], item["version"]), reverse=False)


def get(job_id: str, version: str) -> dict[str, Any] | None:
    return store.get(key(job_id, version))


def _update(record: dict[str, Any], updated: dict[str, Any]) -> dict[str, Any]:
    if not store.compare_and_put(key(record['job_id'], record['version']), record, updated):
        raise ValueError('Job definition changed concurrently; reload before retrying')
    return updated


def reviewed_update(record, operation, parameters, actor):
    """Compute a known maintenance update; caller owns atomic persistence."""
    if operation == 'revise':
        if record.get('job_type') not in {'normalize-ceim','validate-semantic-batch','normalize-unstructured-ceim','connector-ceim-normalize'}:
            raise ValueError('Source-support revisions apply only to semantic source workflows')
        version=parameters.get('version');standards=parameters.get('allowed_standards')
        if record.get('lifecycle_state')!='approved' or not record.get('enabled'):
            raise ValueError('Revise an approved enabled workflow')
        if not isinstance(version,str) or not _SEMVER.fullmatch(version) or tuple(map(int,version.split('.'))) <= tuple(map(int,record['version'].split('.'))):
            raise ValueError('Choose a newer semantic workflow version')
        if not isinstance(standards,list) or not 1<=len(standards)<=12 or any(not isinstance(value,str) or not re.fullmatch('[a-z][a-z0-9-]{1,62}',value) for value in standards) or len(set(standards))!=len(standards):
            raise ValueError('Choose distinct supported source standards')
        from backend.ceim.contract import contract
        for standard in standards:contract.mapping_pack(standard)
        return {**record,'version':version,'allowed_standards':sorted(standards),'schedule':None,
                'derived_from_version':record['version'],'created_at':now(),'approved_at':now(),'approved_by':actor}
    if operation == 'approve':
        if record['lifecycle_state'] == 'disabled':raise ValueError('A disabled job version cannot be approved')
        return {**record,'lifecycle_state':'approved','approved_at':now(),'approved_by':actor}
    if operation == 'disable':
        return {**record,'enabled':False,'lifecycle_state':'disabled','disabled_at':now(),'disabled_by':actor}
    if operation == 'clear':return {**record,'schedule':None,'schedule_cleared_at':now(),'schedule_cleared_by':actor}
    if operation != 'schedule':raise ValueError('Unsupported workflow maintenance operation')
    if record.get('lifecycle_state') != 'approved' or not record.get('enabled'):
        raise ValueError('Only an approved, enabled job can be scheduled')
    schedule={key:parameters.get(key) for key in ('interval_seconds','replay_run_id')}
    errors=_schedule_errors(schedule)+_retry_errors(parameters.get('retry_policy'))
    if errors:raise ValueError('; '.join(errors))
    return {**record,'schedule':{**schedule,'configured_at':now(),'configured_by':actor},
            'retry_policy':dict(parameters.get('retry_policy') or record.get('retry_policy') or {'max_attempts':1,'backoff_seconds':30})}


def _maintain(job_id,version,operation,parameters,actor):
    record=get(job_id,version)
    if not record:raise LookupError('Data job definition was not found')
    return _update(record,reviewed_update(record,operation,parameters,actor))


def approve(job_id,version,approved_by):return _maintain(job_id,version,'approve',{},approved_by)
def disable(job_id,version,disabled_by):return _maintain(job_id,version,'disable',{},disabled_by)
def configure_schedule(job_id,version,payload,configured_by):return _maintain(job_id,version,'schedule',payload,configured_by)
def clear_schedule(job_id,version,configured_by):return _maintain(job_id,version,'clear',{},configured_by)
