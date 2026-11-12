"""Governed reporting selection and database-only visualization APIs."""
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from psycopg import Error as DatabaseError
from pydantic import BaseModel,Field,ConfigDict

class ReportingSelectionBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(min_length=1,max_length=200)
    definition:dict
    approved_by:str|None=None
    approval_token:str|None=None

from backend.depo_platform.authorization import graph_read_identity,approval_identity
from backend.depo_platform.request_bodies import ApprovalBody
from backend.mesh_store import PostgresRegistry
from . import reporting_store as store

router=APIRouter(prefix='/pipeline/reporting',tags=['TRS reporting replica'])


@router.get('/feeds',dependencies=[Depends(graph_read_identity)])
def feeds():
    try:
        from .scheduler import ScheduledJobSupervisor
        return {**store.list_feeds(),'scheduling_enabled':ScheduledJobSupervisor._enabled()}
    except (DatabaseError,RuntimeError,OSError) as exc:raise HTTPException(503,'Reporting database unavailable; verify the reporting migration and service logs') from exc


@router.post('/feeds')
def create_feed(payload:ReportingSelectionBody,request:Request):
    payload=payload.model_dump(exclude_none=True)
    actor=approval_identity(request,payload,token_env='DATA_JOB_APPROVAL_TOKEN')
    try:
        definition=store.validate_definition(payload.get('definition'))
        for identifier in definition['ontology_ids']:
            if not PostgresRegistry('ontology_catalog').get(identifier):raise ValueError('Choose registered ontology versions')
        identifier=store.create(payload.get('name'),definition,actor)
        return store.get(identifier)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    except (DatabaseError,RuntimeError,OSError) as exc:raise HTTPException(503,'Reporting selection could not be retained; inspect service logs before retrying') from exc


@router.post('/feeds/{feed_id}/approve')
def approve_feed(feed_id:str,payload:ApprovalBody,request:Request):
    actor=approval_identity(request,payload,token_env='DATA_JOB_APPROVAL_TOKEN')
    try:
        store.approve(feed_id,actor);return store.get(feed_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    except (DatabaseError,RuntimeError,OSError) as exc:raise HTTPException(503,'Reporting approval was not confirmed; refresh its retained status') from exc


@router.get('/feeds/{feed_id}',dependencies=[Depends(graph_read_identity)])
def reporting_data(feed_id:str,limit:int=Query(50,ge=1,le=200)):
    try:return store.report(feed_id,limit)
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    except (DatabaseError,RuntimeError,OSError) as exc:raise HTTPException(503,'Reporting data unavailable; no empty-data conclusion can be drawn') from exc
