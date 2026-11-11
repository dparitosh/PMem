"""Existing read and approval boundaries for governed learning reviews."""
from typing import Literal
from contextlib import nullcontext
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from backend.depo_platform.authorization import approval_identity, graph_read_identity
from backend.depo_platform.bridge_contract import BridgeConflict
from .bridge_router import jobs
from .learning_review import LearningReview

router=APIRouter(prefix='/api/v1/learning',tags=['governed-learning'])
reviews=LearningReview(jobs)


class Approval(BaseModel):
    model_config=ConfigDict(extra='forbid')
    approved_by: str | None = Field(default=None,max_length=256)
    approval_token: str | None = Field(default=None,max_length=4096)


class Outcome(Approval):
    publication_id: str = Field(min_length=1,max_length=128)
    candidate_id: str = Field(min_length=1,max_length=128)
    result: Literal['confirmed','rejected','uncertain']
    note: str = Field(min_length=1,max_length=1000)


class Lesson(Approval):
    outcome_ids: list[str] = Field(min_length=1,max_length=20)


class Review(Approval):
    action: Literal['approve','revoke']
    reason: str = Field(min_length=1,max_length=1000)


def invoke(fn,*args,budget=25):
    from backend.depo_platform.operations import current_operation,OperationContext,operation_scope
    context = nullcontext() if current_operation() else operation_scope(OperationContext(
        'learning-'+uuid4().hex,(datetime.now(timezone.utc)+timedelta(seconds=budget)).isoformat()))
    try:
        with context:return fn(*args)
    except KeyError:raise HTTPException(404,'Retained learning evidence was not found') from None
    except BridgeConflict as exc:raise HTTPException(409,str(exc)) from None
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    except TimeoutError:raise HTTPException(504,'Review deadline exceeded; verify the retained result before retrying the same request') from None
    except httpx.HTTPError as exc:
        response=getattr(exc,'response',None)
        logging.getLogger(__name__).warning('Learning evidence unavailable: error_class=%s peer_status=%s',type(exc).__name__,getattr(response,'status_code',None))
        raise HTTPException(503,'Source or publication evidence could not be verified; check owning-service access and readiness') from None


@router.get('/status',dependencies=[Depends(graph_read_identity)])
def status():
    return {'capability':'governed_mapping_review','stages':['receipted_publication','human_outcome','lesson_candidate','authorized_review','revision_scoped_hint'],
            'store':'postgresql','advisory_only':True,'model_training_performed':False,'automatic_promotion':False,
            'metrics_basis':'human assessments; not measured model accuracy','max_active_lessons_per_revision':20}


@router.get('/lessons',dependencies=[Depends(graph_read_identity)],summary='Read approved revision-scoped mapping review hints; never business proof or approval')
def lessons(ontology_id: str = Query(min_length=1,max_length=128), import_task_id: str = Query(min_length=1,max_length=128)):
    return invoke(reviews.support,ontology_id,import_task_id)


@router.get('/records/{identifier}',dependencies=[Depends(graph_read_identity)])
def record(identifier:str):
    return invoke(reviews.get,identifier)


@router.post('/outcomes')
def outcome(payload:Outcome,request:Request):
    actor=approval_identity(request,payload.model_dump(),token_env='AGENTIC_APPROVAL_TOKEN')
    return invoke(reviews.outcome,payload.publication_id,payload.candidate_id,payload.result,payload.note,actor,budget=120)


@router.post('/lessons')
def prepare(payload:Lesson,request:Request):
    actor=approval_identity(request,payload.model_dump(),token_env='AGENTIC_APPROVAL_TOKEN')
    return invoke(reviews.prepare,payload.outcome_ids,actor,budget=120)


@router.post('/lessons/{identifier}/review')
def review(identifier:str,payload:Review,request:Request):
    actor=approval_identity(request,payload.model_dump(),token_env='AGENTIC_APPROVAL_TOKEN')
    return invoke(reviews.transition,identifier,payload.action,actor,payload.reason,budget=120)
