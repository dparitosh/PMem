from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.depo_platform.authorization import approval_identity, graph_read_identity
from .bridge_jobs import BridgeJobs, BridgeConflict

router = APIRouter(prefix='/api/v1/workflows', tags=['semantic-bridge-jobs'])
jobs = BridgeJobs()


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ontology_id: str = Field(min_length=1, max_length=256)
    import_task_id: str = Field(min_length=1, max_length=256)


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approved_candidate_ids: list[str] = Field(min_length=1, max_length=2000)
    approved_by: str | None = None
    approval_token: str | None = None


def translate(action):
    try:
        return action()
    except KeyError as exc:
        raise HTTPException(404, 'Bridge job not found') from exc
    except BridgeConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, 'Bridge dependency unavailable. Refresh job status before retrying.') from exc


@router.post('/bridge/previews', status_code=201)
def preview(payload: PreviewInput, actor: str = Depends(graph_read_identity)):
    return translate(lambda: jobs.preview(payload.ontology_id, payload.import_task_id, actor))


@router.get('/bridge/jobs/{job_id}', dependencies=[Depends(graph_read_identity)])
def status(job_id: str):
    return translate(lambda: jobs.get(job_id))


@router.post('/bridge/previews/{preview_id}/publish')
def publish(preview_id: str, payload: ApprovalInput, request: Request):
    actor = approval_identity(request, payload.model_dump(), token_env='AGENTIC_APPROVAL_TOKEN')
    return translate(lambda: jobs.publish(preview_id, payload.approved_candidate_ids, actor))


@router.get('/bridge/jobs/{job_id}/artifact', dependencies=[Depends(graph_read_identity)])
def artifact(job_id: str):
    import json
    job = translate(lambda: jobs.get(job_id))
    return Response(json.dumps(job, indent=2), media_type='application/json',
                    headers={'Content-Disposition': 'attachment; filename="semantic-bridge-job.json"'})


@router.get('/artifacts/{task_id}/{artifact_path:path}', dependencies=[Depends(graph_read_identity)])
def legacy_artifact(task_id: str, artifact_path: str):
    from backend.Services.workflow_artifact_service import WorkflowArtifactService
    path = WorkflowArtifactService.resolve_artifact_path(task_id, artifact_path)
    if path is None:
        raise HTTPException(404, 'Workflow artifact not found')
    return FileResponse(path, filename=path.name)
