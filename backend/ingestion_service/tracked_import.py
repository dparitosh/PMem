"""Tracked SPA import contract hosted by the standalone ingestion service."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from backend.depo_platform.authorization import approval_identity, graph_read_identity
from .router import _ingestion_identity
from .tabular import MAX_UPLOAD_BYTES

router = APIRouter(prefix='/import', tags=['tracked-import'], dependencies=[Depends(_ingestion_identity)])

def _service():
    from backend.Services.unified_data_import import UnifiedDataImportService
    return UnifiedDataImportService

def _status(task_id):
    status = _service().get_status(task_id)
    if not status:
        raise HTTPException(404, 'Import task not found')
    return status

@router.post('/upload')
async def upload(file: UploadFile = File(...), ontology_id: str = Form(''), ontology_mapping: str = Form(''), metadata_exclusion_tags: str = Form('')):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, 'Import exceeds configured upload limit')
    if not content:
        raise HTTPException(400, 'File is empty')
    mapping = ontology_mapping
    if ontology_id:
        from backend.Services.ontology_upload_manager import OntologyUploadManager
        metadata = OntologyUploadManager.load_metadata(ontology_id)
        if not metadata:
            raise HTTPException(404, 'Selected ontology was not found')
        mapping = metadata.get('prefix') or ontology_id
    try:
        task_id = await _service().start_import(content, file.filename or 'source', mapping,
            parse_options={'metadata_exclusion_tags': [tag.strip() for tag in metadata_exclusion_tags.split(',') if tag.strip()]})
        return {'task_id': task_id, 'filename': file.filename, 'ontology_id': ontology_id, 'ontology_mapping': mapping}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@router.get('/status/{task_id}', dependencies=[Depends(graph_read_identity)])
def status(task_id: str):
    return _status(task_id)

@router.get('/preview/{task_id}', dependencies=[Depends(graph_read_identity)])
def preview(task_id: str):
    state = _status(task_id)
    return {'task_id': task_id, 'filename': state.get('filename'), 'status': state.get('status'), **(_service().get_preview(task_id) or {})}

@router.get('/pre-commit/{task_id}', dependencies=[Depends(graph_read_identity)])
def pre_commit(task_id: str):
    state = _status(task_id)
    rows = (_service().get_preview(task_id) or {}).get('row_count', 0)
    task_ok = state.get('status') == 'ready_for_commit' and not state.get('committing') and rows > 0
    try:
        from backend.core.graph import graph
        graph_ok = bool(graph.query('RETURN 1 AS ok'))
    except Exception:
        graph_ok = False
    return {'ready': task_ok and graph_ok, 'reason': '' if task_ok and graph_ok else 'Import must be preview-ready with rows and Neo4j available',
            'checks': {'task': {'ok': task_ok, 'status': state.get('status'), 'rows': rows}, 'neo4j': {'ok': graph_ok}}}

@router.post('/commit/{task_id}')
async def commit(task_id: str, payload: dict, request: Request):
    actor = approval_identity(request, payload, token_env='INGESTION_WRITE_TOKEN')
    _status(task_id)
    try:
        result = await _service().commit_import(task_id)
        return {'success': True, 'task_id': task_id, 'approved_by': actor, **result, 'result': result}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

@router.post('/cancel/{task_id}')
def cancel(task_id: str):
    state = _status(task_id)
    if state.get('committing'):
        raise HTTPException(409, 'Graph commit is in progress; cancellation cannot undo writes')
    _service().cancel_import(task_id)
    return _status(task_id)
