from __future__ import annotations

from backend.depo_platform.request_bodies import OslcQueryBody

from fastapi import APIRouter, HTTPException, Request, Depends
from backend.depo_platform.authorization import approval_identity, graph_read_identity
import httpx

from backend.routes.oslc_routes import router as server_router
from .client import client
from backend.Services.oslc_service import OSLCService
import os
import logging

log = logging.getLogger(__name__)

def remote_enabled():
    return os.getenv("OSLC_REMOTE_ENABLED", "false").lower() == "true"

def require_remote():
    if not remote_enabled():
        raise HTTPException(503, "Remote OSLC is disabled; enable OSLC_REMOTE_ENABLED")
from .access import authorize
from .sync import OSLCSynchronizer, safe_parameters, redact_legacy_snapshots

router = APIRouter(prefix="/oslc", tags=["oslc-client"])
synchronizer = OSLCSynchronizer(client)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "oslc", "server": "enabled" if OSLCService.is_enabled() else "disabled", "remote_enabled": remote_enabled(), "remote_configured": bool(client.base_url)}


@router.get('/capabilities', dependencies=[Depends(graph_read_identity)])
def capabilities() -> dict:
    """Service-wide retained evidence, separate from ontology domain classification."""
    from backend.mesh_store import PostgresRegistry
    from backend.Services.oslc_trs_service import OSLCTRSService
    enabled=OSLCService.is_enabled()
    rows=[
        {'id':'trs','name':'Tracked Resource Set (TRS)','kind':'Change tracking','status':'disabled','counts':{},'workspace':'#/change-control','support':'Tracked change feed; not a business resource domain'},
        {'id':'configuration','name':'Configuration Management','kind':'Baseline selection','status':'disabled','counts':{},'workspace':'#/change-control?source=releases','support':'Frozen baselines and selected versions; no streams, branching or global configuration composition'},
        {'id':'automation','name':'Automation Management','kind':'Workflow execution','status':'disabled','counts':{},'workspace':'#/data-flow','support':'Retained plans, requests and results; native CR/CO and execution authority remain required'},
    ]
    if enabled:
        rows[0]['status']='disabled' if not OSLCTRSService.is_enabled() else 'unavailable'
        if OSLCTRSService.is_enabled():
            try:
                state=OSLCTRSService._load()
                position=state.get('counter')
                if type(position) is not int or position<0:raise ValueError('Invalid tracking position')
                rows[0].update(status='available',counts={'Tracked change position':position})
            except Exception as failure:
                log.warning('OSLC tracking capability unavailable: %s',type(failure).__name__)
        for row in rows[1:]:row['status']='unavailable'
        try:
            release_total,_=PostgresRegistry('release_changes').page(limit=1,field='kind',value='release-baseline')
            analytics_total,_=PostgresRegistry('semantic_configurations').page(limit=1,field='kind',value='analytics-baseline')
            rows[1].update(status='available',counts={'Release baselines':release_total,'Analytics baselines':analytics_total})
        except Exception as failure:
            log.warning('OSLC lifecycle capability unavailable: %s',type(failure).__name__)
        try:
            plans,_=PostgresRegistry('data_job_definitions').page(limit=1,exclude_latest=True)
            runs,_=PostgresRegistry('data_job_runs').page(limit=1,exclude_latest=True)
            rows[2].update(status='available',counts={'Plan resources':plans,'Request resources':runs,'Result resources':runs})
        except Exception as failure:
            log.warning('OSLC lifecycle capability unavailable: %s',type(failure).__name__)
    return {'scope':'service_wide','ontology_scoped':False,'capabilities':rows,
            'conformance':'Implemented subsets; availability does not certify full OSLC conformance'}


@router.get("/remote/catalog", dependencies=[Depends(graph_read_identity)])
def remote_catalog() -> dict:
    require_remote()
    try: return client.discover()
    except (httpx.HTTPError, TimeoutError) as exc: raise HTTPException(status_code=503, detail="Remote OSLC catalog unavailable; check provider readiness") from exc
    except (RuntimeError, ValueError) as exc: raise HTTPException(status_code=503, detail="Remote OSLC response or configuration is invalid") from exc


@router.post("/remote/query/{resource_type}", dependencies=[Depends(graph_read_identity)])
def remote_query(resource_type: str, parameters: OslcQueryBody) -> dict:
    require_remote()
    try: return client.query(resource_type, parameters)
    except (httpx.HTTPError, TimeoutError) as exc: raise HTTPException(status_code=503, detail="Remote OSLC query unavailable; check provider readiness") from exc
    except RuntimeError as exc: raise HTTPException(status_code=503, detail="Remote OSLC response or configuration is invalid") from exc
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/remote/sync/{resource_type}", summary="Pull and stage a remote OSLC query snapshot")
def pull_remote_sync(resource_type: str, parameters: OslcQueryBody, request: Request) -> dict:
    actor = approval_identity(request, parameters, token_env="AGENTIC_APPROVAL_TOKEN")
    require_remote()
    try:
        return synchronizer.pull(resource_type, safe_parameters(parameters), requested_by=actor)
    except (httpx.HTTPError, TimeoutError) as exc: raise HTTPException(status_code=503, detail="Remote OSLC sync unavailable; check provider readiness") from exc
    except RuntimeError as exc: raise HTTPException(status_code=503, detail="Remote OSLC response or configuration is invalid") from exc
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/remote/sync", dependencies=[Depends(graph_read_identity)], summary="List staged OSLC pull snapshots")
def list_remote_syncs(identity: str = Depends(graph_read_identity)) -> dict:
    authorize(identity, "syncs")
    redact_legacy_snapshots(synchronizer.store)
    return {"syncs": synchronizer.store.list()}


@router.get("/remote/sync/{sync_id}", dependencies=[Depends(graph_read_identity)], summary="Read one staged OSLC pull snapshot")
def get_remote_sync(sync_id: str, identity: str = Depends(graph_read_identity)) -> dict:
    authorize(identity, "syncs", sync_id)
    redact_legacy_snapshots(synchronizer.store)
    snapshot = synchronizer.store.get(sync_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="OSLC sync snapshot not found")
    return snapshot
