from fastapi import APIRouter, Depends, HTTPException, Request, Query
from backend.depo_platform.authorization import graph_read_identity, service_write_identity
from backend.depo_platform.request_bodies import ApprovalBody, RestSourceBody
from . import rest_sources

router = APIRouter(prefix='/pipeline/rest-sources', tags=['REST sources'])


@router.get('/submissions/{submission_id}')
def submission_status(submission_id: str, request: Request):
    actor = service_write_identity(request, token_env='DATA_JOB_EXECUTION_TOKEN', default_actor='source-reader')
    from .rest_submissions import retained
    return retained(submission_id, actor)


@router.get('', dependencies=[Depends(graph_read_identity)])
def sources(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    try:
        total, rows = rest_sources.store.page(limit=limit, offset=offset)
        return {'sources': rows, 'total': total, 'limit': limit, 'offset': offset,
                'next_offset': offset + limit if offset + limit < total else None}
    except RuntimeError:
        raise HTTPException(503, 'Source registry unavailable') from None


@router.post('', status_code=201)
def register(payload: RestSourceBody, request: Request):
    actor = service_write_identity(request, token_env='DATA_JOB_APPROVAL_TOKEN', default_actor='source-author')
    try:
        return rest_sources.register(payload, actor)
    except FileExistsError:
        raise HTTPException(409, 'Source ID already exists; use a new ID for a revised registration') from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except RuntimeError:
        raise HTTPException(503, 'Source registry unavailable') from None


@router.post('/{source_id}/preview')
def preview(source_id: str, payload: ApprovalBody, request: Request):
    service_write_identity(request, token_env='DATA_JOB_EXECUTION_TOKEN', default_actor='source-reader')
    try:
        source = rest_sources.store.get(source_id)
        if not source:
            raise HTTPException(404, 'REST source was not found')
        return rest_sources.fetch(source, preview=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except (RuntimeError, OSError):
        raise HTTPException(503, 'REST source is unavailable') from None
