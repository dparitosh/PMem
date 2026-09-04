"""OpenAPI contract for Spark-backed DEPO data jobs."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from backend.artifact_store import ArtifactStore
from backend.platform.authorization import approval_identity

from . import job_definitions
from . import run_records
from .runner import SparkUnavailable, runner


router = APIRouter(prefix="/pipeline", tags=["data-pipeline"])


def _authorize_execution(request: Request, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    actor = approval_identity(request, payload, token_env="DATA_JOB_EXECUTION_TOKEN")
    sanitized = {key: value for key, value in payload.items() if key not in {"approval_token", "approved_by"}}
    return actor, sanitized


def _supervisor_health() -> dict[str, Any]:
    from .app import supervisor
    return supervisor.health()


@router.get("/health", summary="Read Spark data-job execution readiness")
def health() -> dict[str, Any]:
    return {"service": "data-pipeline", **runner.health(), "scheduler": _supervisor_health()}


@router.get("/telemetry", summary="Read UI-ready job telemetry for Siemens IX/ECharts monitoring")
def telemetry() -> dict[str, Any]:
    # Process telemetry is deliberately composed from the in-process Spark
    # view and durable run manifests. This gives the Data Flow UI quality,
    # lineage, checkpoint, and replay evidence after a worker restart.
    try:
        return {**runner.telemetry(), "scheduler": _supervisor_health(), "durable_job_telemetry": run_records.telemetry_summary()}
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


@router.post("/jobs/transform", summary="Run a bounded Spark quality transformation and return JSON")
def transform(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    _, payload = _authorize_execution(request, payload)
    try:
        return runner.transform_quality_summary(payload, correlation_id=getattr(request.state, "request_id", ""))
    except SparkUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _registry_error(exc: RuntimeError) -> HTTPException:
    return HTTPException(status_code=503, detail=f"Data-job control plane is unavailable: {exc}")


def execute_configured_job(definition: dict[str, Any], payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    """Shared bounded dispatcher for OpenAPI requests and scheduled retries."""
    run = run_records.start(definition, payload, correlation_id=correlation_id)
    if definition["job_type"] in {"normalize-ceim", "validate-semantic-batch"}:
        standard = str(payload.get("standard") or "").strip().lower()
        if standard not in definition.get("allowed_standards", []):
            run_records.failed(run, "The request standard is not allowed by this data-job definition")
            raise ValueError("The request standard is not allowed by this data-job definition")
    try:
        if definition["job_type"] == "interactive-quality-summary":
            result = runner.transform_quality_summary(payload, correlation_id=correlation_id)
        elif definition["job_type"] == "validate-unstructured-evidence":
            result = runner.validate_unstructured_evidence(payload, correlation_id=correlation_id)
        elif definition["job_type"] == "enrich-document-evidence":
            result = runner.enrich_document_evidence(payload, correlation_id=correlation_id)
        elif definition["job_type"] == "rdf-quality-statistics":
            result = runner.rdf_quality_statistics(payload, correlation_id=correlation_id)
        elif definition["job_type"] == "rdf-deduplicate-serialize":
            result = runner.rdf_deduplicate_serialize(payload, correlation_id=correlation_id)
        else:
            result = runner.normalize_ceim_batch(payload, correlation_id=correlation_id, validate=definition["job_type"] == "validate-semantic-batch")
    except (SparkUnavailable, ValueError) as exc:
        run_records.failed(run, str(exc))
        raise
    persisted = run_records.complete(run, result)
    return {**result, "configured_job": {field: definition[field] for field in ("job_id", "name", "version", "job_type", "quality_profile", "owner")}, "run_manifest": persisted}


@router.get("/jobs/definitions", summary="List durable, versioned data-job definitions")
def list_job_definitions() -> dict[str, Any]:
    try:
        return {"definitions": job_definitions.all_definitions()}
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


@router.get("/jobs/definitions/{job_id}/{version}", summary="Read a specific data-job definition")
def get_job_definition(job_id: str, version: str) -> dict[str, Any]:
    try:
        record = job_definitions.get(job_id, version)
    except RuntimeError as exc:
        raise _registry_error(exc) from exc
    if not record:
        raise HTTPException(status_code=404, detail="Data job definition was not found")
    return record


@router.post("/jobs/definitions", status_code=201, summary="Create an immutable draft data-job definition")
def create_job_definition(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return job_definitions.create(payload)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


@router.post("/jobs/definitions/{job_id}/{version}/approve", summary="Approve a data-job definition for execution")
def approve_job_definition(job_id: str, version: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    approver = approval_identity(request, payload, token_env="DATA_JOB_APPROVAL_TOKEN")
    try:
        return job_definitions.approve(job_id, version, approver)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


@router.post("/jobs/definitions/{job_id}/{version}/disable", summary="Disable a data-job definition immediately")
def disable_job_definition(job_id: str, version: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    approver = approval_identity(request, payload, token_env="DATA_JOB_APPROVAL_TOKEN")
    try:
        return job_definitions.disable(job_id, version, approver)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


@router.post("/jobs/definitions/{job_id}/{version}/schedule", summary="Configure supervised execution from a retained immutable input")
def configure_job_schedule(job_id: str, version: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="DATA_JOB_APPROVAL_TOKEN")
    replay_run_id = str(payload.get("replay_run_id") or "")
    try:
        prior = run_records.get(replay_run_id)
        if not prior or prior.get("job_id") != job_id or prior.get("job_version") != version:
            raise ValueError("replay_run_id must reference a retained run of the same job and version")
        return job_definitions.configure_schedule(job_id, version, payload, actor)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


@router.post("/jobs/definitions/{job_id}/{version}/schedule/disable", summary="Disable supervised execution for a data-job definition")
def disable_job_schedule(job_id: str, version: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="DATA_JOB_APPROVAL_TOKEN")
    try:
        return job_definitions.clear_schedule(job_id, version, actor)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


@router.post("/jobs/definitions/{job_id}/{version}/run", summary="Run an approved, enabled configured data job")
def run_configured_job(job_id: str, version: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor, payload = _authorize_execution(request, payload)
    try:
        definition = job_definitions.get(job_id, version)
    except RuntimeError as exc:
        raise _registry_error(exc) from exc
    if not definition:
        raise HTTPException(status_code=404, detail="Data job definition was not found")
    if definition.get("lifecycle_state") != "approved" or not definition.get("enabled"):
        raise HTTPException(status_code=409, detail="Only an approved and enabled data-job definition can run")
    correlation_id = getattr(request.state, "request_id", "")
    payload = {**payload, "execution_actor": actor}
    try:
        return execute_configured_job(definition, payload, correlation_id)
    except SparkUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


@router.get("/jobs/runs", summary="List durable data-job run manifests")
def list_job_runs(limit: int = 100) -> dict[str, Any]:
    try:
        return {"runs": run_records.list_runs(limit=limit)}
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


@router.get("/jobs/runs/{run_id}", summary="Read a durable data-job run manifest")
def get_job_run(run_id: str) -> dict[str, Any]:
    try:
        record = run_records.get(run_id)
    except RuntimeError as exc:
        raise _registry_error(exc) from exc
    if not record:
        raise HTTPException(status_code=404, detail="Data job run was not found")
    return record


@router.post("/jobs/runs/{run_id}/publish", summary="Publish an accepted semantic partition and advance its checkpoint")
async def publish_job_run(run_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Use the canonical CEIM API; advance the checkpoint only after success."""
    actor = approval_identity(request, payload, token_env="CEIM_PUBLISH_APPROVAL_TOKEN")
    try:
        record = run_records.get(run_id)
        if not record:
            raise LookupError("Data job run was not found")
        output = dict(record.get("output_manifest") or {})
        if output.get("checkpoint_state") == "advanced":
            return record
        if record.get("status") != "completed" or record.get("job_type") not in {"normalize-ceim", "validate-semantic-batch"}:
            raise ValueError("Only a completed semantic batch can be published")
        artifact_id = str((output.get("partition_artifacts") or {}).get("accepted") or "")
        metadata, path = ArtifactStore().resolve(artifact_id)
        if metadata.get("kind") != "accepted-semantic-partition":
            raise ValueError("Run does not reference an accepted semantic partition")
        batch = json.loads(path.read_text(encoding="utf-8"))
        publication_payload = {
            **batch,
            "ontology_id": payload.get("ontology_id"), "prefix": payload.get("prefix", "ceim"),
            "semantic_release": payload.get("semantic_release"),
            "approved_by": actor, "approval_token": payload.get("approval_token"),
        }
        ceim_url = os.getenv("CEIM_SERVICE_URL", "http://127.0.0.1:8018/api/v1").rstrip("/")
        ceim_root = ceim_url if ceim_url.endswith("/api/v1") else f"{ceim_url}/api/v1"
        forwarded_headers = {
            key: value for key, value in request.headers.items()
            if key.lower() in {"x-ms-client-principal", "x-depo-principal-id", "x-depo-roles"}
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(f"{ceim_root}/ceim/publications/graph", json=publication_payload, headers=forwarded_headers)
        if response.is_error:
            raise RuntimeError(f"Canonical publication returned HTTP {response.status_code}: {response.text[:500]}")
        return run_records.publication_succeeded(record, dict(response.json()))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/jobs/runs/{run_id}/replay", summary="Replay a retained immutable data-job input")
def replay_job_run(run_id: str, request: Request, authorization: dict[str, Any] | None = None) -> dict[str, Any]:
    actor = approval_identity(request, authorization or {}, token_env="DATA_JOB_EXECUTION_TOKEN")
    try:
        previous = run_records.get(run_id)
    except RuntimeError as exc:
        raise _registry_error(exc) from exc
    if not previous:
        raise HTTPException(status_code=404, detail="Data job run was not found")
    try:
        payload = {**run_records.replay_payload(previous), "execution_actor": actor}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        definition = job_definitions.get(previous["job_id"], previous["job_version"])
        if not definition:
            raise LookupError("Data job definition was not found")
        if definition.get("lifecycle_state") != "approved" or not definition.get("enabled"):
            raise ValueError("Only an approved and enabled data-job definition can be replayed")
        return execute_configured_job(definition, payload, getattr(request.state, "request_id", ""))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SparkUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _registry_error(exc) from exc
