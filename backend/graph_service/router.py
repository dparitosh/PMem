from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from backend.platform.authorization import service_write_identity, graph_read_identity

from .neo4j_publisher import publisher

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/health", summary="Graph service health")
def health() -> dict:
    return {"service": "graph", **publisher.health()}


@router.post("/ontologies/publish", summary="Publish a Turtle ontology as an explorable Neo4j hierarchy")
async def publish_ontology(
    request: Request,
    artifact: Annotated[UploadFile, File(description="Turtle ontology artifact")],
    ontology_id: Annotated[str, Form()],
    prefix: Annotated[str, Form()],
) -> dict:
    try:
        service_write_identity(request, token_env="GRAPH_PUBLICATION_TOKEN", default_actor="graph-publication-service")
        return publisher.publish_turtle(content=await artifact.read(), ontology_id=ontology_id, prefix=prefix)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph publication failed: {type(exc).__name__}: {exc}") from exc


@router.get("/overview", dependencies=[Depends(graph_read_identity)], summary="Get a bounded explorer-ready view across published ontologies")
def overview(limit: int = 900) -> dict:
    try:
        return publisher.overview(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph overview failed: {type(exc).__name__}: {exc}") from exc


@router.get("/search", dependencies=[Depends(graph_read_identity)], summary="Search graph resources with bounded parameterized ranking")
def search(query: str, limit: int = 50) -> dict:
    try:
        return publisher.search(query=query, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph search failed: {type(exc).__name__}: {exc}") from exc


@router.get("/ontologies/{ontology_id}/projection", dependencies=[Depends(graph_read_identity)], summary="Get an explorer-ready ontology projection")
def ontology_projection(ontology_id: str, limit: int = 900) -> dict:
    try:
        return publisher.explorer_projection(ontology_id=ontology_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph projection failed: {type(exc).__name__}: {exc}") from exc


@router.get("/traversal/{iri:path}", dependencies=[Depends(graph_read_identity)], summary="Get a bounded explorer-ready neighborhood for an RDF resource")
def traversal(iri: str, depth: int = 1, limit: int = 200) -> dict:
    try:
        return publisher.traversal(iri=iri, depth=depth, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph traversal failed: {type(exc).__name__}: {exc}") from exc


@router.get("/ontologies/{ontology_id}/analytics", dependencies=[Depends(graph_read_identity)], summary="Run Semantica analytics on a live Neo4j ontology projection")
def ontology_analytics(ontology_id: str, limit: int = 3000) -> dict:
    try:
        return publisher.analytics(ontology_id=ontology_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph analytics failed: {type(exc).__name__}: {exc}") from exc


@router.get("/ontologies/{ontology_id}/neighborhood", dependencies=[Depends(graph_read_identity)], summary="Get bounded semantic distance neighbors from the live ontology graph")
def ontology_neighborhood(ontology_id: str, iri: str, max_hops: int = 3, limit: int = 200) -> dict:
    try:
        return publisher.neighborhood(ontology_id=ontology_id, iri=iri, max_hops=max_hops, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph neighborhood failed: {type(exc).__name__}: {exc}") from exc
