from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..Services.oslc_query_service import OSLCQueryService, OSLCQueryValidationError
from ..Services.oslc_service import OSLCService
from ..Services.oslc_trs_service import OSLCTRSService


router = APIRouter(prefix="/oslc", tags=["OSLC"])


@router.get("/catalog")
async def get_service_provider_catalog():
    if not OSLCService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC integration is disabled.")
    result = OSLCService.service_provider_catalog()
    result["lifecycleProvider"] = OSLCService.config().base_url + "/oslc/lifecycle"
    return result


@router.get("/providers/{provider_id}")
async def get_service_provider(provider_id: str):
    if not OSLCService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC integration is disabled.")
    service_provider = OSLCService.service_provider()
    if provider_id != OSLCService.config().provider_id:
        raise HTTPException(status_code=404, detail="OSLC service provider not found.")
    return service_provider


@router.get("/shapes")
async def list_resource_shapes():
    if not OSLCService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC integration is disabled.")
    try:
        return OSLCService.list_shapes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to list OSLC resource shapes") from exc


@router.get("/shapes/{shape_id}")
async def get_resource_shape(shape_id: str, request: Request):
    if not OSLCService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC integration is disabled.")
    try:
        return OSLCService.resource_shape(shape_id)
    except ValueError as exc:
        from backend.depo_platform.authorization import graph_read_identity
        from backend.oslc_service.access import authorize
        from backend.oslc_service.ontology_shapes import catalog_shape
        identity = graph_read_identity(request)
        authorize(identity, "ontologies", shape_id)
        try:
            return catalog_shape(shape_id, OSLCService.config().base_url)
        except ValueError as missing:
            raise HTTPException(status_code=404, detail=str(missing)) from missing
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to retrieve the OSLC resource shape") from exc


@router.get("/query/{resource_type}")
async def query_resources(resource_type: str, request: Request):
    if not OSLCService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC integration is disabled.")
    try:
        params = OSLCQueryService.parse(dict(request.query_params), max_page_size=OSLCService.config().max_page_size)
        return OSLCService.query_resources(resource_type, params)
    except OSLCQueryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="OSLC service unavailable. Please try again later.") from exc


@router.get("/resources/{element_id:path}")
async def get_resource(element_id: str, include_links: bool = Query(default=True)):
    if not OSLCService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC integration is disabled.")
    payload = OSLCService.get_resource(element_id)
    if not payload:
        raise HTTPException(status_code=404, detail="OSLC resource not found.")
    if not include_links:
        payload = dict(payload)
        payload.pop("outgoingLinks", None)
    return payload


@router.get("/trs")
async def get_trs_descriptor():
    if not OSLCTRSService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC TRS is disabled.")
    try:
        return OSLCTRSService.tracked_resource_set()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="OSLC service unavailable. Please try again later.") from exc


@router.get("/trs/base")
async def get_trs_base(limit: int = Query(default=200, ge=1, le=1000)):
    if not OSLCTRSService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC TRS is disabled.")
    try:
        return OSLCTRSService.base_resources(limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="OSLC service unavailable. Please try again later.") from exc


@router.get("/trs/changelog")
async def get_trs_changelog(after: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=1000)):
    if not OSLCTRSService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC TRS is disabled.")
    try:
        return OSLCTRSService.change_log(after=after, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="OSLC service unavailable. Please try again later.") from exc


@router.get("/dictionaries/{prefix}")
async def get_oslc_dictionary(
    prefix: str,
    instance_limit: int = Query(default=2000, ge=100, le=20000),
    relationship_limit: int = Query(default=500, ge=50, le=5000),
    fallback_limit: int = Query(default=200, ge=50, le=2000),
):
    if not OSLCService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC integration is disabled.")
    try:
        return OSLCService.get_dictionary(
            prefix=prefix,
            instance_limit=instance_limit,
            relationship_limit=relationship_limit,
            fallback_limit=fallback_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to retrieve the OSLC dictionary") from exc


@router.get("/taxonomies")
async def list_oslc_taxonomies():
    if not OSLCService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC integration is disabled.")
    try:
        return OSLCService.list_taxonomies()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to list OSLC taxonomies") from exc


@router.get("/taxonomies/{ontology_id}")
async def get_oslc_taxonomy(ontology_id: str):
    if not OSLCService.is_enabled():
        raise HTTPException(status_code=404, detail="OSLC integration is disabled.")
    try:
        return OSLCService.get_taxonomy(ontology_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to retrieve the OSLC taxonomy") from exc
