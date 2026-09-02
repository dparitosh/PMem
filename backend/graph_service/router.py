from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .neo4j_publisher import publisher

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/health", summary="Graph service health")
def health() -> dict:
    return {"service": "graph", **publisher.health()}


@router.post("/ontologies/publish", summary="Publish a Turtle ontology as an explorable Neo4j hierarchy")
async def publish_ontology(
    artifact: Annotated[UploadFile, File(description="Turtle ontology artifact")],
    ontology_id: Annotated[str, Form()],
    prefix: Annotated[str, Form()],
) -> dict:
    try:
        return publisher.publish_turtle(content=await artifact.read(), ontology_id=ontology_id, prefix=prefix)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph publication failed: {type(exc).__name__}: {exc}") from exc


@router.get("/overview", summary="Get a bounded explorer-ready view across published ontologies")
def overview(limit: int = 900) -> dict:
    try:
        return publisher.overview(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph overview failed: {type(exc).__name__}: {exc}") from exc


@router.get("/ontologies/{ontology_id}/projection", summary="Get an explorer-ready ontology projection")
def ontology_projection(ontology_id: str, limit: int = 900) -> dict:
    try:
        return publisher.explorer_projection(ontology_id=ontology_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph projection failed: {type(exc).__name__}: {exc}") from exc


@router.get("/traversal/{iri:path}", summary="Get a bounded explorer-ready neighborhood for an RDF resource")
def traversal(iri: str, depth: int = 1, limit: int = 200) -> dict:
    try:
        return publisher.traversal(iri=iri, depth=depth, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph traversal failed: {type(exc).__name__}: {exc}") from exc


@router.get("/ontologies/{ontology_id}/analytics", summary="Run Semantica analytics on a live Neo4j ontology projection")
def ontology_analytics(ontology_id: str, limit: int = 3000) -> dict:
    try:
        return publisher.analytics(ontology_id=ontology_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph analytics failed: {type(exc).__name__}: {exc}") from exc


@router.get("/ontologies/{ontology_id}/neighborhood", summary="Get bounded semantic distance neighbors from the live ontology graph")
def ontology_neighborhood(ontology_id: str, iri: str, max_hops: int = 3, limit: int = 200) -> dict:
    try:
        return publisher.neighborhood(ontology_id=ontology_id, iri=iri, max_hops=max_hops, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph neighborhood failed: {type(exc).__name__}: {exc}") from exc
