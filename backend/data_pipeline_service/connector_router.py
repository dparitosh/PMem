from fastapi import APIRouter,Depends,HTTPException,Request,Query
from backend.depo_platform.authorization import graph_read_identity,service_write_identity
from backend.depo_platform.request_bodies import ConnectorSourceBody
from . import connector_sources as sources

router=APIRouter(prefix='/pipeline/connector-sources',tags=['Registered source connectors'])


@router.get('/profiles',dependencies=[Depends(graph_read_identity)])
def profiles():
    try:return {'profiles':sources.public_profiles()}
    except ValueError:raise HTTPException(503,'Connector profile configuration needs operator review') from None


@router.get('',dependencies=[Depends(graph_read_identity)])
def registered(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    try:
        total,rows=sources.store.page(limit=limit,offset=offset)
        return {'sources':rows,'total':total,'next_offset':offset+limit if offset+limit<total else None}
    except RuntimeError:raise HTTPException(503,'Connector source registry is unavailable') from None


@router.post('',status_code=201)
def register(payload:ConnectorSourceBody,request:Request):
    actor=service_write_identity(request,token_env='DATA_JOB_APPROVAL_TOKEN',default_actor='source-author')
    try:return sources.register(payload,actor)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    except FileExistsError:raise HTTPException(409,'Source is immutable; use a new source identity') from None
    except RuntimeError:raise HTTPException(503,'Connector source registry is unavailable') from None


@router.get('/submissions/{submission_id}')
def submission(submission_id:str,request:Request):
    actor=service_write_identity(request,token_env='DATA_JOB_EXECUTION_TOKEN',default_actor='source-reader')
    from .rest_submissions import retained
    return retained(submission_id,actor,receipt_store=sources.submissions)
