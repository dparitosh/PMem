import logging
from typing import Annotated
from starlette.concurrency import run_in_threadpool
from backend.depo_platform.upload_limits import ontology_upload_limit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from backend.depo_platform.authorization import service_write_identity, graph_read_identity

from .neo4j_publisher import publisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get('/ontology-report/{ontology_id}', dependencies=[Depends(graph_read_identity)], summary='Full loaded-ontology OSLC domain coverage and linked resource counts')
def loaded_ontology_report(ontology_id: str) -> dict:
    from .ontology_reports import ontology_report
    try:
        return ontology_report(ontology_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.exception('Ontology OSLC report failed')
        raise HTTPException(503, 'Ontology report unavailable; check graph and ontology registry connectivity') from exc


@router.get("/health", summary="Graph service health")
def health() -> dict:
    return {"service": "graph", **publisher.health()}


@router.get("/access", summary="Verify graph read credentials without querying Neo4j")
def access(identity: str = Depends(graph_read_identity)) -> dict:
    return {"status": "authorized", "service": "graph"}


@router.post("/ontologies/publish", summary="Publish a Turtle ontology as an explorable Neo4j hierarchy")
async def publish_ontology(
    request: Request,
    artifact: Annotated[UploadFile, File(description="Turtle ontology artifact")],
    ontology_id: Annotated[str, Form()],
    prefix: Annotated[str, Form()],
    publication_id: Annotated[str | None, Form()] = None,
) -> dict:
    try:
        service_write_identity(request, token_env="GRAPH_PUBLICATION_TOKEN", default_actor="graph-publication-service")
        limit = ontology_upload_limit()
        content = await artifact.read(limit + 1)
        if len(content) > limit:
            raise HTTPException(413, "Ontology artifact exceeds ONTOLOGY_MAX_UPLOAD_BYTES")
        return await run_in_threadpool(publisher.publish_turtle, content=content, ontology_id=ontology_id, prefix=prefix, publication_id=publication_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph publication failed: {type(exc).__name__}: {exc}") from exc


@router.get("/ontologies/{ontology_id}/publications/{publication_id}", dependencies=[Depends(graph_read_identity)], summary="Read a durable graph publication receipt")
def publication_receipt(ontology_id: str, publication_id: str) -> dict:
    try:
        from backend.depo_platform.graph_publication_lock import publication_lock
        from starlette.responses import JSONResponse
        # An idle receipt read and a writer use the same cross-process lock.
        # A 404 is retry evidence only when no publisher owns that lock.
        with publication_lock(ontology_id) as idle:
            if not idle:
                progress = publisher.publication_receipt(ontology_id=ontology_id, publication_id=publication_id)
                return JSONResponse(status_code=409, content={'detail': 'Publication is still active',
                    'status': 'publishing', 'ontology_id': ontology_id, 'publication_id': publication_id,
                    'progress': {key: progress.get(key) for key in ('resource_offset', 'resources_expected', 'relationships_expected', 'activation_resource_offset', 'activation_relationship_offsets')} if progress and progress.get('status') == 'staging' else None})
            receipt = publisher.publication_receipt(ontology_id=ontology_id, publication_id=publication_id)
            from backend.depo_platform.graph_access import reconcile_activation
            reconcile_activation(ontology_id, publication_id, receipt)
            if receipt is None or receipt.get('status') == 'staging':
                return JSONResponse(status_code=404, content={'detail': 'Publication receipt was not found', 'publication_idle': True,
                    'resumable': bool(receipt and receipt.get('status') == 'staging')})
            return receipt
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph publication receipt is unavailable: {type(exc).__name__}: {exc}") from exc


@router.get("/overview", dependencies=[Depends(graph_read_identity)], summary="Get a bounded explorer-ready view across published ontologies")
def overview(limit: int = 900) -> dict:
    try:
        return publisher.overview(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph overview failed: {type(exc).__name__}: {exc}") from exc


@router.get('/metrics', dependencies=[Depends(graph_read_identity)], summary='Complete declared-entity counts for published RDF projections')
def metrics(ontology_id: str = '', ontology_prefix: str = '') -> dict:
    try:
        return publisher.metrics(ontology_id=ontology_id, ontology_prefix=ontology_prefix)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, 'Graph metrics unavailable; check graph connectivity and service logs') from exc


from .bridge_router import bridge_service_identity


@router.get('/mapping-terms', dependencies=[Depends(bridge_service_identity)], summary='Private peer read of scoped ontology mapping targets from the graph data layer')
def mapping_terms(scope: str) -> dict:
    try:
        return publisher.mapping_terms(scope)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, 'Graph mapping data unavailable; check graph service dependencies') from exc


@router.get('/explorer-search', dependencies=[Depends(graph_read_identity)], summary='Search graph nodes, relationships, property names and values')
def explorer_search(query: str, scope: str = '', limit: int = 80, instances_only: bool = False) -> dict:
    from .explorer_search import search as universal_search
    try:
        return universal_search(query,scope,limit,instances_only)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except Exception as exc:
        logger.exception('Explorer search failed')
        raise HTTPException(503,'Graph search unavailable; inspect service logs with X-Request-ID') from exc


@router.get("/search", dependencies=[Depends(graph_read_identity)], summary="Search graph resources with bounded parameterized ranking")
def search(query: str, limit: int = 50, ontology_id: str = '', ontology_prefix: str = '', business_only: bool = False) -> dict:
    try:
        return publisher.search(query=query, limit=limit, ontology_id=ontology_id, ontology_prefix=ontology_prefix, business_only=business_only)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Graph search failed")
        raise HTTPException(status_code=503, detail="Graph search failed; check service logs using X-Request-ID") from exc


@router.get("/ontologies/{ontology_id}/projection", dependencies=[Depends(graph_read_identity)], summary="Get an explorer-ready ontology projection")
def ontology_projection(ontology_id: str, limit: int = 900) -> dict:
    try:
        return publisher.explorer_projection(ontology_id=ontology_id, limit=limit)
    except Exception as exc:
        logger.exception("Graph projection failed")
        raise HTTPException(status_code=503, detail="Graph projection failed; check service logs using X-Request-ID") from exc


@router.get('/view/architecture/{prefix}', dependencies=[Depends(graph_read_identity)], summary='Read imported architecture and process instances')
def architecture_process_view(prefix: str, limit: int = 750) -> dict:
    from backend.Services.graph_view_service import GraphViewService
    try:
        return GraphViewService.get_architecture_process_view(prefix=prefix, limit=limit)
    except Exception as exc:
        logger.exception('Architecture process view failed')
        raise HTTPException(503, 'Process graph unavailable; check graph service logs using X-Request-ID') from exc


@router.get("/traversal/{iri:path}", dependencies=[Depends(graph_read_identity)], summary="Get a bounded explorer-ready neighborhood for an RDF resource")
def traversal(iri: str, depth: int = 1, limit: int = 200) -> dict:
    try:
        return publisher.traversal(iri=iri, depth=depth, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Traversal identity is ambiguous or invalid; select a graph node from the current ontology view") from exc
    except Exception as exc:
        logger.exception("Graph traversal failed")
        raise HTTPException(status_code=503, detail="Graph traversal failed; check service logs using X-Request-ID") from exc


@router.get("/ontologies/{ontology_id}/analytics", dependencies=[Depends(graph_read_identity)], summary="Run Semantica analytics on a live Neo4j ontology projection")
def ontology_analytics(ontology_id: str, limit: int = 3000) -> dict:
    try:
        return publisher.analytics(ontology_id=ontology_id, limit=limit)
    except Exception as exc:
        logger.exception("Graph analytics failed")
        raise HTTPException(status_code=503, detail="Graph analytics failed; check service logs using X-Request-ID") from exc


@router.get("/ontologies/{ontology_id}/neighborhood", dependencies=[Depends(graph_read_identity)], summary="Get bounded semantic distance neighbors from the live ontology graph")
def ontology_neighborhood(ontology_id: str, iri: str, max_hops: int = 3, limit: int = 200) -> dict:
    try:
        return publisher.neighborhood(ontology_id=ontology_id, iri=iri, max_hops=max_hops, limit=limit)
    except Exception as exc:
        logger.exception("Graph neighborhood failed")
        raise HTTPException(status_code=503, detail="Graph neighborhood failed; check service logs using X-Request-ID") from exc
