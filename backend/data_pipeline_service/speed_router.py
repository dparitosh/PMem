from __future__ import annotations

from backend.depo_platform.request_bodies import ApprovalBody, JobPublicationBody, SpeedEventBody, SpeedReconciliationBody, SpeedSourceBody, EventJobBody

from typing import Any
from fastapi import APIRouter, HTTPException, Request, Query, Depends
from backend.depo_platform.authorization import approval_identity, graph_read_identity
from . import speed_path

router = APIRouter(prefix="/pipeline/speed", tags=["speed-path"])

@router.get("/sources", dependencies=[Depends(graph_read_identity)])
def list_sources() -> dict[str, Any]: return {"sources": speed_path.list_sources()}

@router.post("/sources", status_code=201)
def create_source(payload: SpeedSourceBody, request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_PATH_APPROVAL_TOKEN")
    try: return speed_path.register_source(payload, actor)
    except FileExistsError as exc: raise HTTPException(409, str(exc)) from exc
    except speed_path.SpeedConflict as exc: raise HTTPException(409,str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/sources/{source_id}/approve")
def approve_source(source_id: str, payload: ApprovalBody, request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_PATH_APPROVAL_TOKEN")
    try: return speed_path.approve_source(source_id, actor)
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc

@router.get("/events", dependencies=[Depends(graph_read_identity)])
def list_events(limit: int = Query(100,ge=1,le=1000), offset: int = Query(0,ge=0)) -> dict[str, Any]: return {"events": speed_path.list_events(limit,offset)}

@router.post("/events", status_code=202)
def capture_event(payload: SpeedEventBody, request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_EVENT_TOKEN")
    try: return speed_path.capture_event(payload, actor)
    except speed_path.SpeedConflict as exc: raise HTTPException(409,str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/reconciliations", status_code=202)
def reconcile(payload: SpeedReconciliationBody, request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_EVENT_TOKEN")
    try: return speed_path.reconcile(list(payload.get("event_ids") or []), actor)
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc
    except speed_path.SpeedConflict as exc: raise HTTPException(409,str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post('/reconciliations/{reconciliation_id}/jobs',status_code=202)
def prepare_event_job(reconciliation_id:str,payload:EventJobBody,request:Request):
    actor=approval_identity(request,{},token_env='DATA_JOB_EXECUTION_TOKEN')
    from .event_jobs import submit
    try:
        record=submit(reconciliation_id,payload.job_id,payload.version,payload.expected_digest,actor,getattr(request.state,'request_id',''),request.headers.get('configuration-context'))
        return {'status':record['status'],'run':record,'run_manifest':record}
    except (ValueError,OSError) as exc:raise HTTPException(409,'Retained event input could not be verified; restore its evidence before retrying') from exc

@router.post('/reconciliations/{reconciliation_id}/publish')
async def publish(reconciliation_id:str,payload:JobPublicationBody,request:Request):
    approval_identity(request,payload,token_env='CEIM_PUBLISH_APPROVAL_TOKEN')
    from .event_jobs import linked_run
    review=speed_path.reconciliations.get(reconciliation_id)
    if not review:raise HTTPException(404,'Event review was not found')
    record=linked_run(review)
    if not record:raise HTTPException(409,'Process these events with an approved workflow, then submit and authorize its Change Control request')
    from .router import publish_job_run
    return await publish_job_run(record['run_id'],payload,request)


@router.get('/reconciliations/{reconciliation_id}', dependencies=[Depends(graph_read_identity)])
def reconciliation_evidence(reconciliation_id: str):
    try:return speed_path.review_context(reconciliation_id)
    except LookupError as exc:raise HTTPException(404,str(exc)) from exc


@router.get('/reconciliations', dependencies=[Depends(graph_read_identity)])
def reconciliation_list(limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0)):
    total,rows=speed_path.reconciliations.page(limit=limit,offset=offset,order_field='created_at',
        projection={key:[key] for key in ('reconciliation_id','status','standard','created_at','counts','name','processing_job')})
    from .event_jobs import lineage
    for row in rows:row['lineage']=lineage(row)
    return {'reconciliations':rows,'total':total,'next_offset':offset+limit if offset+limit<total else None}
