from __future__ import annotations

import os
import json
from backend.depo_platform.service_urls import service_url
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from .catalog import catalog, ontology_upload_limit
from .intelligence import SemanticIntelligence
from .merge_service import GovernedMergeService
from .business_context import BusinessContextService
from .semantica_adapter import semantica
from backend.Services.ontology_upload_manager import OntologyUploadManager
from backend.depo_platform.authorization import approval_identity, graph_read_identity
from backend.depo_platform.network import service_bearer_headers
from .vocabulary_service import vocabularies
from backend.mesh_store import PostgresRegistry
import hashlib

router = APIRouter(prefix="/ontologies", tags=["ontologies"])
intelligence = SemanticIntelligence(semantica.workspace.root)
merges = GovernedMergeService(catalog, intelligence, catalog.root)
business_context = BusinessContextService(catalog.root)
graph_publications = PostgresRegistry('ontology_graph_publications_v1')


@router.get('/{ontology_id}/publication', summary='Verify a retained ontology graph publication')
async def ontology_publication_status(ontology_id: str) -> dict:
    record = await run_in_threadpool(graph_publications.get, ontology_id)
    if record:
        metadata, content = await run_in_threadpool(catalog.read_artifact, ontology_id)
        digest = hashlib.sha256(content).hexdigest()
        if record.get('artifact_sha256', record.get('publication_id')) != digest:
            record = {'ontology_id': ontology_id, 'publication_id': digest}
    if not record:
        metadata = await run_in_threadpool(catalog.get, ontology_id)
        if not metadata:
            return {'ontology_id': ontology_id, 'status': 'not_verified'}
        _, content = await run_in_threadpool(catalog.read_artifact, ontology_id)
        source = str(metadata.get('source') or '')
        identifier = source.split(':', 1)[1] if source.startswith('engineering-workflow:') else hashlib.sha256(content).hexdigest()
        record = {'ontology_id': ontology_id, 'publication_id': identifier}
    graph_root = service_url('GRAPH_SERVICE_URL', 'http://127.0.0.1:8013').rstrip('/')
    if not graph_root.endswith('/api/v1'): graph_root += '/api/v1'
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.get(f"{graph_root}/graph/ontologies/{ontology_id}/publications/{record['publication_id']}", headers=service_bearer_headers('GRAPH_READ_TOKEN', service_name='graph receipts', endpoint=graph_root))
        if response.status_code == 404:
            body = response.json()
            if isinstance(body, dict) and body.get('detail') == 'Publication receipt was not found':
                return {**record, 'status': 'not_published'}
            raise ValueError('Receipt route is unavailable')
        response.raise_for_status()
        receipt = response.json()
        if not isinstance(receipt, dict) or receipt.get('ontology_id') != ontology_id or receipt.get('publication_id') != record['publication_id'] or receipt.get('status') != 'published' or any(type(receipt.get(field)) is not int or receipt[field] < 0 for field in ('resources', 'relationships')):
            raise ValueError('Invalid graph receipt')
        if receipt.get('current') is False:
            return {**record, 'status': 'not_published', 'receipt': None}
        return {**record, 'status': 'published', 'receipt': receipt}
    except (httpx.HTTPError, ValueError):
        return {**record, 'status': 'unverified'}


@router.post('/{ontology_id}/publish', summary='Publish an approved retained ontology to Neo4j')
async def publish_registered_ontology(ontology_id: str, payload: dict[str, Any], request: Request) -> dict:
    import asyncio
    try:
        return await run_in_threadpool(catalog.with_publication_lock, ontology_id,
            lambda: asyncio.run(_publish_registered_ontology(ontology_id, payload, request)))
    except ValueError as exc:
        raise HTTPException(409, 'Ontology lifecycle is being updated; refresh before publication') from exc


async def _publish_registered_ontology(ontology_id: str, payload: dict[str, Any], request: Request) -> dict:
    actor = approval_identity(request, payload, token_env='ONTOLOGY_APPROVAL_TOKEN')
    metadata = await run_in_threadpool(catalog.get, ontology_id)
    if not metadata: raise HTTPException(404, 'Prepare this retained ontology in the catalog before review and publication')
    if metadata.get('lifecycle_status') != 'approved': raise HTTPException(409, 'Approve the ontology before graph publication')
    from rdflib import Graph
    _, content = await run_in_threadpool(catalog.read_artifact, ontology_id)
    turtle = await run_in_threadpool(lambda: Graph().parse(data=content, format=metadata['validation']['rdf_format']).serialize(format='turtle').encode('utf-8'))
    publication_id = hashlib.sha256(content).hexdigest()
    previous = await run_in_threadpool(graph_publications.get, ontology_id)
    record = {'ontology_id': ontology_id, 'publication_id': publication_id, 'artifact_sha256': publication_id, 'approved_by': actor, 'status': 'publishing'}
    if previous and previous.get('publication_id') == publication_id:
        record['approved_by'] = previous.get('approved_by') or actor
    graph_root = service_url('GRAPH_SERVICE_URL', 'http://127.0.0.1:8013').rstrip('/')
    if not graph_root.endswith('/api/v1'): graph_root += '/api/v1'
    try:
        existing = await ontology_publication_status(ontology_id)
        if existing['status'] == 'published': return existing
        if existing['status'] == 'unverified':
            raise ValueError('Graph receipt lookup failed; publication must be reconciled first')
        current_metadata, current_content = await run_in_threadpool(catalog.read_artifact, ontology_id)
        if current_metadata.get('lifecycle_status') != 'approved' or hashlib.sha256(current_content).hexdigest() != publication_id:
            raise HTTPException(409, 'Ontology approval or artifact changed; review again before publication')
        await run_in_threadpool(graph_publications.put, ontology_id, record)
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            response = await client.post(f'{graph_root}/graph/ontologies/publish',
                data={'ontology_id': ontology_id, 'prefix': metadata['prefix'], 'publication_id': publication_id},
                files={'artifact': ('ontology.ttl', turtle, 'text/turtle')},
                headers=service_bearer_headers('GRAPH_PUBLICATION_TOKEN', service_name='graph publication', endpoint=graph_root))
        response.raise_for_status()
        receipt = response.json()
        if not isinstance(receipt, dict) or receipt.get('status') != 'success' or receipt.get('ontology_id') != ontology_id or receipt.get('publication_id') != publication_id or any(type(receipt.get(field)) is not int or receipt[field] < 0 for field in ('resources', 'relationships')):
            raise ValueError('Invalid graph receipt')
        record = {**record, 'status': 'published', 'receipt': receipt}
        await run_in_threadpool(graph_publications.put, ontology_id, record)
        return record
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, 'Publication outcome is unverified. Verify its graph receipt before retrying.') from exc


def _array_field(payload: dict[str, Any], name: str) -> list:
    value = payload.get(name, [])
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail=f"{name} must be an array")
    return value


@router.get("/health", summary="Ontology service health")
def health() -> dict:
    return {"status": "ok", "service": "ontology", "semantica": semantica.capabilities()}


@router.get("/capabilities", summary="Ontology generation and validation capabilities")
def capabilities() -> dict:
    return semantica.capabilities()


@router.post("/generate", summary="Generate, validate, evaluate and export an ontology using Semantica")
def generate_ontology(payload: dict[str, Any]) -> dict:
    data = payload.get("data") or {"entities": payload.get("entities", []), "relationships": payload.get("relationships", [])}
    result = semantica.generate(
        data=data, name=str(payload.get("name") or "GeneratedOntology"),
        base_uri=str(payload.get("base_uri") or "https://depo.local/ontology/"),
        persist=False,
    )
    return {"ontology": result["ontology"], "validation": result["validation"], "evaluation": result["evaluation"],
            "version_id": result["version_id"], "lifecycle_status": "draft_preview",
            "next_action": "Register the reviewed RDF/OWL artifact, then transition it through in_review and approved.",
            "artifacts": {name: content.decode("utf-8") for name, content in result["artifacts"].items()}}


@router.post("/validate-graph", summary="Validate Turtle graph data against a Semantica-generated SHACL ontology")
def validate_graph(payload: dict[str, Any]) -> dict:
    try:
        ontology = payload.get("ontology") or semantica.workspace.get(str(payload["version_id"]))
        return semantica.workspace.validate_graph(data_graph=str(payload["data_graph"]), ontology=ontology)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/namespaces", summary="List ontology namespaces")
def list_namespaces() -> dict:
    return {"namespaces": semantica.workspace.namespaces.get_all_namespaces()}


@router.post("/namespaces", summary="Register an ontology namespace")
def register_namespace(payload: dict[str, str]) -> dict:
    try:
        semantica.workspace.namespaces.register_namespace(payload["prefix"], payload["uri"])
        return {"prefix": payload["prefix"], "uri": semantica.workspace.namespaces.get_namespace(payload["prefix"])}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/alignments", summary="Create a Semantica ontology alignment")
def create_alignment(payload: dict[str, str]) -> dict:
    try:
        record = semantica.workspace.align(source_uri=payload["source_uri"], target_uri=payload["target_uri"], predicate=payload.get("predicate", "skos:exactMatch"))
        return {"alignment": record, "alignments": semantica.workspace.alignments}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/alignments", summary="List ontology alignments")
def list_alignments() -> dict:
    return {"alignments": semantica.workspace.list_alignments()}


@router.post("/reason", summary="Run explainable Semantica rule inference")
def reason(payload: dict[str, Any]) -> dict:
    try:
        return {"inferences": semantica.workspace.reason(facts=_array_field(payload, "facts"), rules=_array_field(payload, "rules"))}
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/quality-gate", summary="Run Semantica deduplication and conflict checks before publication")
def quality_gate(payload: dict[str, Any]) -> dict:
    try:
        return intelligence.quality_gate(
            entities=_array_field(payload, "entities"), deduplicate=bool(payload.get("deduplicate", True)),
            conflict_property=payload.get("conflict_property"), merge_strategy=str(payload.get("merge_strategy", "keep_most_complete")),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/versions", summary="Create a native Semantica ontology version snapshot")
def create_version(payload: dict[str, Any]) -> dict:
    try:
        ontology = payload.get("ontology") or semantica.workspace.get(str(payload["version_id"]))
        return intelligence.create_version(ontology=ontology, label=str(payload["label"]), author=str(payload.get("author", "system@depo.local")), description=str(payload.get("description", "")))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/versions", summary="List native Semantica ontology version snapshots")
def list_versions() -> dict:
    return {"versions": intelligence.list_versions()}


@router.post("/versions/compare", summary="Compare two native Semantica ontology versions")
def compare_versions(payload: dict[str, str]) -> dict:
    try:
        return intelligence.compare_versions(payload["older"], payload["newer"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/analytics", summary="Run Semantica graph analytics on a supplied canonical graph")
def graph_analytics(payload: dict[str, Any]) -> dict:
    try:
        return intelligence.analytics(payload.get("graph") or payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/policies", summary="List persisted Semantica decision policies")
def list_policies() -> dict:
    return {"policies": intelligence._policies()}


@router.post("/policies", summary="Create or update a Semantica decision policy")
def add_policy(payload: dict[str, Any]) -> dict:
    try:
        return intelligence.add_policy(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/policies/evaluate", summary="Evaluate Semantica policies before a governed action")
def evaluate_policies(payload: dict[str, Any]) -> dict:
    try:
        return intelligence.evaluate_policies(dict(payload.get("decision") or {}), _array_field(payload, "exception_policy_ids"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/merges/preview", summary="Create a persistent governed ontology merge preview")
def preview_merge(payload: dict[str, Any]) -> dict:
    try:
        return merges.preview(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/merges/{preview_id}/apply", summary="Apply an approved, conflict-free ontology merge")
async def apply_merge(preview_id: str, payload: dict[str, Any], request: Request) -> dict:
    try:
        approver = approval_identity(request, payload, token_env="ONTOLOGY_APPROVAL_TOKEN")
        publish = payload.get('publish', False)
        if type(publish) is not bool:
            raise ValueError('publish must be a boolean')
        result = await run_in_threadpool(merges.apply, preview_id, approver)
        ontology_id = result['ontology']['ontology_id']
        if not publish:
            return {**result, 'publication_status': 'not_requested'}
        metadata = await run_in_threadpool(catalog.get, ontology_id)
        # Explicit reviewed application authorizes the resulting merge, while
        # preserving the catalog's normal transition and syntax checks.
        if metadata.get('lifecycle_status') == 'draft':
            await run_in_threadpool(catalog.transition, ontology_id=ontology_id, target='in_review', actor=approver, reason=f'Reviewed merge {preview_id}')
            metadata = await run_in_threadpool(catalog.get, ontology_id)
        if metadata.get('lifecycle_status') == 'in_review':
            await run_in_threadpool(catalog.transition, ontology_id=ontology_id, target='approved', actor=approver, reason=f'Approved merge {preview_id}')
        publication = await publish_registered_ontology(ontology_id, payload, request)
        return {**result, 'ontology': await run_in_threadpool(catalog.get, ontology_id),
                'publication_status': publication['status'], 'publication': publication}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/merges/{preview_id}/policy', summary='Inspect automatic ontology merge policy')
def merge_policy(preview_id: str, reader: str = Depends(graph_read_identity)) -> dict:
    try:
        return merges.evaluate_policy(preview_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/merges/{preview_id}/receipt', summary='Verify retained merged draft without repeating writes')
def merge_receipt(preview_id: str, reader: str = Depends(graph_read_identity)) -> dict:
    try:
        return merges.receipt(preview_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post('/merges/{preview_id}/apply-automatic', summary='Create a conflict-free union draft under delegated approval')
def automatic_merge(preview_id: str, payload: dict[str, Any], request: Request) -> dict:
    try:
        approver = approval_identity(request, payload, token_env='ONTOLOGY_APPROVAL_TOKEN')
        return merges.apply_automatic(preview_id, approver)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/business-context", summary="Get Semantica business-object context graph status")
def business_context_summary() -> dict:
    return business_context.summary()


@router.post("/business-context/objects", summary="Upsert typed business objects and relationships into Semantica ContextGraph")
def upsert_business_context(payload: dict[str, Any], request: Request) -> dict:
    approval_identity(request, payload, token_env="AGENTIC_APPROVAL_TOKEN")
    try:
        return business_context.upsert(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/business-context/objects/{object_id}", summary="Traverse contextual relationships for a business object")
def get_business_object(object_id: str, hops: int = 2, limit: int = 200) -> dict:
    try:
        return business_context.get(object_id, hops=hops, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404 if str(exc) == "Business object not found" else 422, detail=str(exc)) from exc


@router.get("/business-context/objects/{object_id}/where-used", summary="Find incoming business-object relationships")
def business_object_where_used(object_id: str, limit: int = 200) -> dict:
    try:
        return business_context.where_used(object_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404 if str(exc) == "Business object not found" else 422, detail=str(exc)) from exc


@router.get("/business-context/search", summary="Search persisted Semantica business context")
def search_business_context(query: str, limit: int = 50) -> dict:
    try:
        return business_context.search(query, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/mcp", summary="Get the local Semantica MCP stdio-server launch contract")
def mcp_contract() -> dict:
    return {
        "transport": "stdio", "command": "python", "args": ["-m", "semantica.mcp_server"],
        "environment": {"SEMANTICA_KG_PATH": "<optional persisted Semantica graph path>"},
        "note": "Configure this command in an MCP client; it is intentionally not exposed as an unauthenticated HTTP endpoint.",
    }


@router.get("/vocabularies", summary="List versioned governed SKOS vocabularies")
def list_vocabularies() -> dict[str, Any]:
    records = vocabularies.list()
    return {"vocabularies": records, "count": len(records)}


@router.post("/vocabularies", status_code=201, summary="Create an immutable draft SKOS vocabulary release")
def create_vocabulary(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="VOCABULARY_APPROVAL_TOKEN")
    try:
        return vocabularies.create(payload, actor)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/vocabularies/{scheme_id}/{version}", summary="Read one governed SKOS vocabulary release")
def get_vocabulary(scheme_id: str, version: str) -> dict[str, Any]:
    record = vocabularies.get(scheme_id, version)
    if not record:
        raise HTTPException(status_code=404, detail="Vocabulary release was not found")
    return record


@router.post("/vocabularies/{scheme_id}/{version}/transition", summary="Review or approve a SKOS vocabulary release")
def transition_vocabulary(scheme_id: str, version: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="VOCABULARY_APPROVAL_TOKEN")
    try:
        return vocabularies.transition(scheme_id, version, str(payload.get("target") or ""), actor, str(payload.get("reason") or ""))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/vocabularies/{scheme_id}/{version}/publish", summary="Publish an approved SKOS vocabulary through the graph service")
async def publish_vocabulary(scheme_id: str, version: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="VOCABULARY_APPROVAL_TOKEN")
    record = vocabularies.get(scheme_id, version)
    if not record:
        raise HTTPException(status_code=404, detail="Vocabulary release was not found")
    if record.get("publication_status") == "published":
        return record
    if record.get("lifecycle_status") != "approved":
        raise HTTPException(status_code=409, detail="Only an approved vocabulary can be published")
    artifact, content = vocabularies.publication_artifact(record)
    graph_url = service_url("GRAPH_SERVICE_URL", "http://127.0.0.1:8013/api/v1")
    graph_root = graph_url if graph_url.endswith("/api/v1") else f"{graph_url}/api/v1"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{graph_root}/graph/ontologies/publish",
                data={"ontology_id": f"skos-{scheme_id}-{version.replace('.', '-')}", "prefix": "skos"},
                files={"artifact": (artifact["filename"], content, "text/turtle")},
                headers=service_bearer_headers("GRAPH_PUBLICATION_TOKEN", service_name="the graph publication API", endpoint=graph_root),
            )
        if response.is_error:
            raise RuntimeError(f"Graph service returned HTTP {response.status_code}")
        return vocabularies.mark_published(record, actor, artifact, dict(response.json()))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Vocabulary publication is unavailable: {type(exc).__name__}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", summary="List ontology artifacts registered by this service")
def list_ontologies() -> dict:
    ontologies = catalog.list()
    return {"ontologies": ontologies, "count": len(ontologies)}


@router.post("/migrations/legacy", summary="Adopt legacy ingestion artifacts into the native ontology catalog")
def migrate_legacy_ontologies(payload: dict[str, Any]) -> dict:
    """Perform an additive, idempotent catalog migration for named standards."""
    requested = payload.get("ontology_ids")
    if not isinstance(requested, list) or not all(isinstance(value, str) for value in requested):
        raise HTTPException(status_code=422, detail="ontology_ids must be an array of registered ontology IDs")
    ontology_ids = list(dict.fromkeys(value.strip() for value in requested if value.strip()))
    if not ontology_ids:
        raise HTTPException(status_code=422, detail="ontology_ids must contain at least one registered ontology ID")
    # Validate the whole request before the first catalog write. Otherwise a
    # missing later ID leaves an unexpected partial migration behind.
    sources = []
    for ontology_id in ontology_ids:
        result = OntologyUploadManager.get_ontology(ontology_id)
        metadata = result.get("metadata") if result.get("status") == "success" else None
        content = OntologyUploadManager.get_file_for_reuse(ontology_id)
        if not metadata or content is None:
            raise HTTPException(status_code=404, detail=f"Legacy ontology artifact not found: {ontology_id}")
        sources.append((ontology_id, metadata, content))
    migrated: list[dict[str, Any]] = []
    for ontology_id, metadata, content in sources:
        migrated.append(catalog.adopt_legacy(
            ontology_id=ontology_id,
            content=content,
            filename=str(metadata.get("file_name") or metadata.get("filename") or metadata.get("file_path") or f"{ontology_id}.artifact"),
            ontology_name=str(metadata.get("ontology_name") or ontology_id),
            prefix=str(metadata.get("prefix") or "ontology"),
            description=str(metadata.get("description") or ""),
            extra_metadata={
                "legacy_source": "ingestion",
                "legacy_file_type": metadata.get("file_type"),
                "legacy_generation_type": metadata.get("generation_type"),
                "legacy_uploaded_at": metadata.get("uploaded_at"),
            },
        ))
    return {"status": "success", "migrated": migrated, "count": len(migrated)}


@router.post("/migrations/legacy/analytics", summary="Backfill missing draft catalog analytics from retained ontology artifacts")
def backfill_legacy_analytics(payload: dict[str, Any], request: Request) -> dict:
    actor = approval_identity(request, payload, token_env="ONTOLOGY_APPROVAL_TOKEN")
    ontology_ids = [str(value).strip() for value in payload.get("ontology_ids", []) if str(value).strip()]
    if not ontology_ids:
        raise HTTPException(status_code=422, detail="ontology_ids must contain at least one registered ontology ID")
    try:
        return catalog.backfill_analytics(ontology_ids=ontology_ids, actor=actor)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{ontology_id}", summary="Read ontology artifact metadata")
def get_ontology(ontology_id: str) -> dict:
    ontology = catalog.get(ontology_id)
    if ontology is None:
        raise HTTPException(status_code=404, detail="Ontology artifact not found")
    return ontology


@router.post("/register", status_code=201, summary="Register an OWL/RDF artifact")
async def register_ontology(
    artifact: Annotated[UploadFile, File(description="TTL, RDF/XML, OWL or JSON-LD ontology artifact")],
    ontology_name: Annotated[str, Form()],
    prefix: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "api",
    extra_metadata: Annotated[str, Form()] = "{}",
) -> dict:
    try:
        if len(extra_metadata) > 262144:
            raise ValueError('Registration metadata exceeds 256 KiB')
        metadata = json.loads(extra_metadata)
        if not isinstance(metadata, dict):
            raise ValueError('extra_metadata must be a JSON object')
        limit = ontology_upload_limit()
        content = await artifact.read(limit + 1)
        if len(content) > limit:
            raise HTTPException(status_code=413, detail='Ontology artifact exceeds ONTOLOGY_MAX_UPLOAD_BYTES')
        return await run_in_threadpool(catalog.register,
            content=content, filename=artifact.filename or "ontology.ttl",
            ontology_name=ontology_name, prefix=prefix, description=description, source=source,
            extra_metadata=metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{ontology_id}/transition", summary="Submit, approve, deprecate, or retire a syntax-validated ontology artifact")
def transition_ontology(ontology_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="ONTOLOGY_APPROVAL_TOKEN")
    try:
        return catalog.transition(
            ontology_id=ontology_id,
            target=str(payload.get("target") or ""),
            actor=actor,
            reason=str(payload.get("reason") or ""),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
