"""SysML v2 API connector readiness routes."""

from fastapi import APIRouter, Query

from ..Services.sysml_v2_connector_service import get_sysml_v2_connector_service

router = APIRouter(prefix="/sysml-v2", tags=["SysML v2"])


@router.get("/status")
def sysml_v2_status(probe: bool = Query(False, description="When true, performs a best-effort GET /projects probe.")):
    service = get_sysml_v2_connector_service()
    if probe:
        return service.probe_projects()
    return service.status()


@router.get("/integration-plan")
def sysml_v2_integration_plan():
    return get_sysml_v2_connector_service().integration_plan()
