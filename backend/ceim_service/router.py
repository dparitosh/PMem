"""OpenAPI boundary for versioned Canonical Engineering Information Model mappings."""
from __future__ import annotations

import os
import re
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from backend.artifact_store import ArtifactStore
from backend.ceim.contract import contract
from backend.ceim.resolution import analyze_entities, resolution_registry
from backend.ceim.qif_adapter import qif_to_ceim_batch, validate_qif_instance
from backend.ceim.reqif_adapter import reqif_to_ceim_batch
from backend.ceim.plmxml_adapter import plmxml_to_ceim_batch
from backend.depo_platform.authorization import approval_identity
from backend.depo_platform.network import bounded_timeout_seconds
from backend.depo_platform.semantic_registry import resolve_approved_release


router = APIRouter(prefix="/ceim", tags=["ceim"])
MAX_BATCH_RECORDS = 5_000
MAX_SOURCE_BYTES = 25 * 1024 * 1024
_ONTOLOGY_ID = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


@router.get("/contract", summary="Read CEIM contract metadata")
def read_contract() -> dict[str, Any]:
    return {
        "version": contract.version,
        "namespace": contract.namespace,
        "ontology_artifact": "ceim-v0.1.ttl",
        "mapping_packs": [path.stem for path in sorted(contract.mapping_root.glob("*.json"))],
    }


@router.get("/mapping-packs/{standard}", summary="Read a governed CEIM source mapping pack")
def read_mapping_pack(standard: str) -> dict[str, Any]:
    try:
        return contract.mapping_pack(standard)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/normalize/entity", summary="Normalize one declared source entity into CEIM")
def normalize_entity(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return contract.normalize_entity(standard=str(payload.get("standard") or ""), record=dict(payload.get("record") or {}))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/normalize/relationship", summary="Normalize one declared source relationship into CEIM")
def normalize_relationship(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return contract.normalize_relationship(standard=str(payload.get("standard") or ""), record=dict(payload.get("record") or {}))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/normalize/batch", summary="Normalize a bounded batch for Spark or ingestion publication")
def normalize_batch(payload: dict[str, Any]) -> dict[str, Any]:
    standard = str(payload.get("standard") or "")
    entities, relationships = list(payload.get("entities") or []), list(payload.get("relationships") or [])
    if len(entities) + len(relationships) > MAX_BATCH_RECORDS:
        raise HTTPException(status_code=422, detail=f"Batch exceeds maximum of {MAX_BATCH_RECORDS} records")
    try:
        if payload.get("representation") == "normalized-ceim-v1":
            if payload.get("ceim_version") != contract.version:
                raise ValueError("Normalized CEIM input version does not match the active CEIM contract")
            normalized_entities = [dict(record) for record in entities]
            normalized_relationships = [dict(record) for record in relationships]
            contract.validate_mapping_evidence(
                standard=standard, entities=normalized_entities, relationships=normalized_relationships,
            )
            contract.to_rdf(entities=normalized_entities, relationships=normalized_relationships)
            analysis = resolution_registry.record(analyze_entities(normalized_entities))
            analysis = resolution_registry.apply(analysis, list(payload.get("resolution_case_ids") or []))
            return {"ceim_version": contract.version, "entities": analysis["entities"], "relationships": normalized_relationships, "entity_resolution": {key: analysis[key] for key in ("duplicate_merges", "conflicts", "blocking", "resolution_case_ids")}}
        normalized_entities = [contract.normalize_entity(standard=standard, record=dict(record)) for record in entities]
        normalized_relationships = [contract.normalize_relationship(standard=standard, record=dict(record)) for record in relationships]
        analysis = resolution_registry.record(analyze_entities(normalized_entities))
        analysis = resolution_registry.apply(analysis, list(payload.get("resolution_case_ids") or []))
        return {"ceim_version": contract.version, "entities": analysis["entities"], "relationships": normalized_relationships, "entity_resolution": {key: analysis[key] for key in ("duplicate_merges", "conflicts", "blocking", "resolution_case_ids")}}
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _normalized_batch(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized = normalize_batch(payload)
    return list(normalized["entities"]), list(normalized["relationships"])


@router.get("/entity-resolution/cases", summary="List durable CEIM duplicate and conflict review cases")
def resolution_cases() -> dict[str, Any]:
    return {"cases": resolution_registry.list()}


@router.post("/entity-resolution/cases/{case_id}/resolve", summary="Record a steward-approved CEIM entity resolution")
def resolve_entity_case(case_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="CEIM_RESOLUTION_APPROVAL_TOKEN")
    try:
        return resolution_registry.resolve(case_id, str(payload.get("strategy") or ""), actor, str(payload.get("rationale") or ""), payload.get("selected_candidate_index"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/validate/batch", summary="Validate a normalized CEIM batch against CEIM SHACL shapes")
def validate_batch(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        entities, relationships = _normalized_batch(payload)
        return contract.validate_projection(entities=entities, relationships=relationships)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/adapters/reqif/normalize", summary="Extract a ReqIF instance into a non-persisted CEIM batch")
async def normalize_reqif(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if len(content) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="ReqIF upload exceeds the 25 MiB limit")
    try:
        source = ArtifactStore().ingest_bytes(
            content, filename=file.filename or "source.reqif", kind="source-reqif",
            media_type=file.content_type or "application/xml", provenance={"adapter": "reqif-ceim-v1"},
        )
        return {
            **reqif_to_ceim_batch(content), "source_artifact_id": source["artifact_id"],
            "representation": "normalized-ceim-v1", "ceim_version": contract.version,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/adapters/qif/normalize", summary="Extract a declared QIF instance into a non-persisted CEIM batch")
async def normalize_qif(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if len(content) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="QIF upload exceeds the 25 MiB limit")
    try:
        source = ArtifactStore().ingest_bytes(
            content, filename=file.filename or "source.qif", kind="source-qif",
            media_type=file.content_type or "application/xml", provenance={"adapter": "qif-ceim-v1"},
        )
        return {
            **qif_to_ceim_batch(content), "source_artifact_id": source["artifact_id"],
            "representation": "normalized-ceim-v1", "ceim_version": contract.version,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/adapters/plmxml/normalize", summary="Extract a Teamcenter PLMXML instance into a non-persisted CEIM batch")
async def normalize_plmxml(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if len(content) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="PLMXML upload exceeds the 25 MiB limit")
    try:
        source = ArtifactStore().ingest_bytes(
            content, filename=file.filename or "source.plmxml", kind="source-plmxml",
            media_type=file.content_type or "application/xml", provenance={"adapter": "plmxml-ceim-v1"},
        )
        return {
            **plmxml_to_ceim_batch(content), "source_artifact_id": source["artifact_id"],
            "representation": "normalized-ceim-v1", "ceim_version": contract.version,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/adapters/qif/validate", summary="Validate a QIF 3.0 instance against the bundled document XSD")
async def validate_qif(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if len(content) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="QIF upload exceeds the 25 MiB limit")
    try:
        return validate_qif_instance(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/projection/turtle", summary="Create a deterministic CEIM RDF projection for governed graph publication")
def turtle_projection(payload: dict[str, Any]) -> Response:
    try:
        entities, relationships = _normalized_batch(payload)
        return Response(content=contract.turtle_projection(entities=entities, relationships=relationships), media_type="text/turtle")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _publish_to_graph(*, turtle: str, ontology_id: str, prefix: str, publication_id: str | None = None) -> dict[str, Any]:
    """Use the graph service's sole publication boundary, never the database directly."""
    graph_url = os.getenv("GRAPH_SERVICE_URL", "http://127.0.0.1:8013").rstrip("/")
    # Deployment service discovery may provide either a host root or the
    # standard API root.  Normalize it once to avoid the subtle `/api/v1/api/v1`
    # route that otherwise turns a governed publication into a false 404.
    graph_api_root = graph_url if graph_url.endswith("/api/v1") else f"{graph_url}/api/v1"
    # Large ontology projections can exceed the default request window while
    # Neo4j commits. Keep the boundary configurable for customer deployments.
    publication_timeout = bounded_timeout_seconds("GRAPH_PUBLICATION_TIMEOUT_SECONDS", default=180)
    async with httpx.AsyncClient(timeout=publication_timeout) as client:
        response = await client.post(
            f"{graph_api_root}/graph/ontologies/publish",
            data={"ontology_id": ontology_id, "prefix": prefix, "publication_id": publication_id or ""},
            files={"artifact": (f"{ontology_id}.ttl", turtle.encode("utf-8"), "text/turtle")},
            headers={"Authorization": f"Bearer {os.environ['GRAPH_PUBLICATION_TOKEN']}"} if os.getenv("GRAPH_PUBLICATION_TOKEN") else {},
        )
    if response.is_error:
        raise httpx.HTTPStatusError(
            f"Graph service returned {response.status_code}", request=response.request, response=response,
        )
    return dict(response.json())


@router.post("/publications/graph", summary="Validate and explicitly publish a CEIM RDF projection through the graph service")
async def publish_graph(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Publish only a SHACL-conformant CEIM batch with an explicit approval.

    Normalization and projection endpoints remain read-only.  This separate
    mutation endpoint ensures graph publication is traceable and goes through
    the graph microservice rather than coupling CEIM to a graph database.
    """
    standard = str(payload.get("standard") or "").strip().lower()
    entities, relationships = list(payload.get("entities") or []), list(payload.get("relationships") or [])
    if not standard or len(entities) + len(relationships) > MAX_BATCH_RECORDS:
        raise HTTPException(status_code=422, detail=f"A standard and at most {MAX_BATCH_RECORDS} records are required")
    ontology_id = str(payload.get("ontology_id") or f"ceim-{standard}").strip().lower()
    if not _ONTOLOGY_ID.fullmatch(ontology_id):
        raise HTTPException(status_code=422, detail="ontology_id must be 2-64 lowercase letters, digits, underscores, or hyphens")
    prefix = str(payload.get("prefix") or "ceim").strip()
    if not prefix:
        raise HTTPException(status_code=422, detail="prefix is required")
    approved_by = approval_identity(request, payload, token_env="CEIM_PUBLISH_APPROVAL_TOKEN")
    try:
        semantic_release = await resolve_approved_release(payload.get("semantic_release"))
        normalized = normalize_batch({
            "standard": standard, "entities": entities, "relationships": relationships,
            "representation": payload.get("representation"), "ceim_version": payload.get("ceim_version"), "resolution_case_ids": payload.get("resolution_case_ids"),
        })
        validation = contract.validate_projection(entities=list(normalized["entities"]), relationships=list(normalized["relationships"]))
        if not validation.get("conforms"):
            raise HTTPException(status_code=422, detail={"message": "CEIM SHACL validation failed; graph publication was not attempted", "validation": validation})
        turtle = contract.turtle_projection(entities=list(normalized["entities"]), relationships=list(normalized["relationships"]), decision={"approved_by": approved_by, "semantic_release": semantic_release})
        publication_id = str(payload.get("publication_id") or "").strip() or None
        publication = await _publish_to_graph(turtle=turtle, ontology_id=ontology_id, prefix=prefix, publication_id=publication_id)
        return {
            "status": "published",
            "ontology_id": ontology_id,
            "prefix": prefix,
            "approved_by": approved_by,
            "semantic_release": semantic_release,
            "publication_id": publication_id,
            "validation": {key: validation[key] for key in ("conforms", "triple_count", "ceim_version")},
            "publication": publication,
        }
    except HTTPException:
        raise
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Graph publication is unavailable: {type(exc).__name__}") from exc
