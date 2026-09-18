"""OpenAPI contract for Spark-backed DEPO data jobs."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from backend.artifact_store import ArtifactStore
from backend.depo_platform.authorization import approval_identity
from backend.depo_platform.network import bounded_timeout_seconds

from . import job_definitions
from . import run_records
from .runner import SparkUnavailable, runner
from .handlers import registry as handler_registry


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


@router.post("/workflows/document-evidence/run", summary="Run the governed document evidence to CEIM workflow")
def run_document_evidence_workflow(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Execute the fixed unstructured workflow with approved job versions."""
    actor, payload = _authorize_execution(request, payload)
    try:
        return execute_document_evidence_workflow(
            payload, correlation_id=getattr(request.state, "request_id", ""), actor=actor,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SparkUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _registry_error(exc) from exc


def _registry_error(exc: RuntimeError) -> HTTPException:
    return HTTPException(status_code=503, detail=f"Data-job control plane is unavailable: {exc}")


async def _reconcile_graph_publication(
    *, ontology_id: str, publication_id: str, headers: dict[str, str], timeout_seconds: float,
) -> dict[str, Any] | None:
    """Read the graph's durable receipt after an uncertain upstream response.

    This is intentionally a read, not a retry.  A matching receipt proves the
    canonical mutation completed; an absent receipt leaves the run safely
    awaiting publication for an operator to retry with the same run identity.
    """
    graph_url = os.getenv("GRAPH_SERVICE_URL", "http://127.0.0.1:8013").rstrip("/")
    graph_root = graph_url if graph_url.endswith("/api/v1") else f"{graph_url}/api/v1"
    try:
        async with httpx.AsyncClient(timeout=min(timeout_seconds, 15)) as client:
            response = await client.get(
                f"{graph_root}/graph/ontologies/{ontology_id}/publications/{publication_id}", headers=headers,
            )
        return dict(response.json()) if response.status_code == 200 else None
    except httpx.HTTPError:
        return None


def execute_configured_job(definition: dict[str, Any], payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    """Shared bounded dispatcher for OpenAPI requests and scheduled retries."""
    run = run_records.start(definition, payload, correlation_id=correlation_id)
    if definition["job_type"] in {"normalize-ceim", "validate-semantic-batch", "normalize-unstructured-ceim"}:
        standard = str(payload.get("standard") or "").strip().lower()
        if standard not in definition.get("allowed_standards", []):
            run_records.failed(run, "The request standard is not allowed by this data-job definition")
            raise ValueError("The request standard is not allowed by this data-job definition")
    try:
        result = handler_registry.get(definition["job_type"]).execute(
            runner, payload, correlation_id=correlation_id,
        )
    except Exception as exc:
        run_records.failed(run, str(exc))
        raise
    persisted = run_records.complete(run, result)
    return {**result, "configured_job": {field: definition[field] for field in ("job_id", "name", "version", "job_type", "quality_profile", "owner")}, "run_manifest": persisted}


def _approved_definition(reference: Any) -> dict[str, Any]:
    """Resolve one workflow stage to an approved, enabled job definition."""
    if not isinstance(reference, dict):
        raise ValueError("Each workflow stage must contain a job_id and version")
    job_id, version = str(reference.get("job_id") or ""), str(reference.get("version") or "")
    definition = job_definitions.get(job_id, version)
    if not definition:
        raise LookupError(f"Workflow job definition was not found: {job_id}:{version}")
    if definition.get("lifecycle_state") != "approved" or not definition.get("enabled"):
        raise ValueError(f"Workflow stage is not approved and enabled: {job_id}:{version}")
    return definition


def execute_document_evidence_workflow(payload: dict[str, Any], *, correlation_id: str, actor: str) -> dict[str, Any]:
    """Run the governed unstructured path with explicit artifact hand-offs.

    This small, fixed topology is intentional: documents are quality checked,
    structurally enriched, then mapped and semantically validated.  It does
    not accept arbitrary executable code or client-provided topology.  Every
    stage is an approved versioned job and raw document text remains in the
    immutable evidence artifact rather than the graph projection.
    """
    stages = payload.get("stages")
    if not isinstance(stages, dict):
        raise ValueError("stages must provide validation, enrichment, and normalization job references")
    expected = {
        "validation": "validate-unstructured-evidence",
        "enrichment": "enrich-document-evidence",
        "normalization": "normalize-unstructured-ceim",
    }
    definitions = {name: _approved_definition(stages.get(name)) for name in expected}
    for name, job_type in expected.items():
        if definitions[name]["job_type"] != job_type:
            raise ValueError(f"Workflow stage {name} must use job type {job_type}")

    source = {
        key: value for key, value in payload.items()
        if key in {"documents", "evidence_artifact_id", "artifact_ids", "source_system", "checkpoint", "next_checkpoint"}
    }
    source["execution_actor"] = actor
    validation = execute_configured_job(definitions["validation"], source, correlation_id)
    if validation.get("status") != "completed":
        return {"workflow": "document-evidence-to-ceim-v1", "status": "quality_warning", "stages": {"validation": validation}, "publication": "blocked; review unstructured evidence quality"}

    enrichment = execute_configured_job(definitions["enrichment"], source, correlation_id)
    if enrichment.get("status") != "completed":
        return {"workflow": "document-evidence-to-ceim-v1", "status": "quality_warning", "stages": {"validation": validation, "enrichment": enrichment}, "publication": "blocked; review document enrichment quality"}
    proposal_artifact_id = str(((enrichment.get("run_manifest") or {}).get("output_manifest") or {}).get("partition_artifacts", {}).get("accepted") or "")
    if not proposal_artifact_id:
        raise RuntimeError("Document enrichment did not retain an accepted proposal artifact")

    normalization = execute_configured_job(
        definitions["normalization"],
        {"proposal_artifact_id": proposal_artifact_id, "standard": "unstructured-evidence", "execution_actor": actor},
        correlation_id,
    )
    state = "completed" if normalization.get("status") == "completed" else "quality_warning"
    return {
        "workflow": "document-evidence-to-ceim-v1", "status": state,
        "stages": {"validation": validation, "enrichment": enrichment, "normalization": normalization},
        "accepted_semantic_run_id": (normalization.get("run_manifest") or {}).get("run_id"),
        "publication": "not_attempted; publish the accepted semantic run through the canonical approval endpoint",
    }


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
        if record.get("status") != "completed" or record.get("job_type") not in {"normalize-ceim", "validate-semantic-batch", "normalize-unstructured-ceim"}:
            raise ValueError("Only a completed semantic batch can be published")
        artifact_id = str((output.get("partition_artifacts") or {}).get("accepted") or "")
        metadata, path = ArtifactStore().resolve(artifact_id)
        if metadata.get("kind") != "accepted-semantic-partition":
            raise ValueError("Run does not reference an accepted semantic partition")
        batch = json.loads(path.read_text(encoding="utf-8"))
        ontology_id = str(payload.get("ontology_id") or f"ceim-{batch.get('standard') or record.get('source_standard') or 'batch'}").strip().lower()
        publication_payload = {
            **batch,
            "ontology_id": ontology_id, "prefix": payload.get("prefix", "ceim"),
            "semantic_release": payload.get("semantic_release"),
            # A stable run id makes a successful graph commit recoverable if
            # the caller loses the CEIM response while the commit completes.
            "publication_id": run_id,
            "approved_by": actor, "approval_token": payload.get("approval_token"),
        }
        ceim_url = os.getenv("CEIM_SERVICE_URL", "http://127.0.0.1:8018/api/v1").rstrip("/")
        ceim_root = ceim_url if ceim_url.endswith("/api/v1") else f"{ceim_url}/api/v1"
        forwarded_headers = {
            key: value for key, value in request.headers.items()
            if key.lower() in {"x-ms-client-principal", "x-depo-principal-id", "x-depo-roles"}
        }
        publication_token = os.getenv("GRAPH_PUBLICATION_TOKEN", "").strip()
        if publication_token:
            forwarded_headers["Authorization"] = f"Bearer {publication_token}"
        publication_timeout = bounded_timeout_seconds("GRAPH_PUBLICATION_TIMEOUT_SECONDS", default=180)
        try:
            async with httpx.AsyncClient(timeout=publication_timeout) as client:
                response = await client.post(f"{ceim_root}/ceim/publications/graph", json=publication_payload, headers=forwarded_headers)
        except httpx.TimeoutException as exc:
            # Never retry a mutation blindly. Query the graph's durable
            # receipt keyed by this run before reporting an uncertain result.
            receipt = await _reconcile_graph_publication(
                ontology_id=ontology_id, publication_id=run_id, headers=forwarded_headers, timeout_seconds=publication_timeout,
            )
            if receipt:
                return run_records.publication_succeeded(record, {
                    "status": "published", "ontology_id": ontology_id,
                    "publication_id": run_id, "reconciled_after_timeout": True, "publication": receipt,
                })
            raise RuntimeError("Canonical publication timed out and no durable graph receipt was found; retry the same run to reconcile safely") from exc
        if response.is_error:
            if response.status_code in {502, 503, 504}:
                receipt = await _reconcile_graph_publication(
                    ontology_id=ontology_id, publication_id=run_id, headers=forwarded_headers, timeout_seconds=publication_timeout,
                )
                if receipt:
                    return run_records.publication_succeeded(record, {
                        "status": "published", "ontology_id": ontology_id,
                        "publication_id": run_id, "reconciled_after_gateway_error": True, "publication": receipt,
                    })
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
