from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .catalog import catalog
from .intelligence import SemanticIntelligence
from .merge_service import GovernedMergeService
from .business_context import BusinessContextService
from .semantica_adapter import semantica

router = APIRouter(prefix="/ontologies", tags=["ontologies"])
intelligence = SemanticIntelligence(semantica.workspace.root)
merges = GovernedMergeService(catalog, intelligence, catalog.root)
business_context = BusinessContextService(catalog.root)


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
    )
    return {"ontology": result["ontology"], "validation": result["validation"], "evaluation": result["evaluation"],
            "version_id": result["version_id"], "artifacts": {name: content.decode("utf-8") for name, content in result["artifacts"].items()}}


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
    return {"alignments": semantica.workspace.alignments}


@router.post("/reason", summary="Run explainable Semantica rule inference")
def reason(payload: dict[str, Any]) -> dict:
    try:
        return {"inferences": semantica.workspace.reason(facts=list(payload.get("facts", [])), rules=list(payload.get("rules", [])))}
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/quality-gate", summary="Run Semantica deduplication and conflict checks before publication")
def quality_gate(payload: dict[str, Any]) -> dict:
    try:
        return intelligence.quality_gate(
            entities=list(payload.get("entities", [])), deduplicate=bool(payload.get("deduplicate", True)),
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
    return intelligence.evaluate_policies(dict(payload.get("decision") or {}), list(payload.get("exception_policy_ids") or []))


@router.post("/merges/preview", summary="Create a persistent governed ontology merge preview")
def preview_merge(payload: dict[str, Any]) -> dict:
    try:
        return merges.preview(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/merges/{preview_id}/apply", summary="Apply an approved, conflict-free ontology merge")
def apply_merge(preview_id: str, payload: dict[str, Any]) -> dict:
    try:
        return merges.apply(preview_id, str(payload.get("approved_by") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/business-context", summary="Get Semantica business-object context graph status")
def business_context_summary() -> dict:
    return business_context.summary()


@router.post("/business-context/objects", summary="Upsert typed business objects and relationships into Semantica ContextGraph")
def upsert_business_context(payload: dict[str, Any]) -> dict:
    try:
        return business_context.upsert(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


@router.get("", summary="List ontology artifacts registered by this service")
def list_ontologies() -> dict:
    ontologies = catalog.list()
    return {"ontologies": ontologies, "count": len(ontologies)}


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
) -> dict:
    try:
        return catalog.register(
            content=await artifact.read(), filename=artifact.filename or "ontology.ttl",
            ontology_name=ontology_name, prefix=prefix, description=description, source=source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
