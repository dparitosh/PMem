"""HTTP plugin boundary; all imports use DEPO's governed data jobs."""
import base64
import binascii
import os
import secrets
from pathlib import Path
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


def authorize(request: Request):
    token = os.getenv('MBSE_PLUGIN_TOKEN', '')
    if not token:
        raise HTTPException(503, 'MBSE_PLUGIN_TOKEN is not configured')
    if not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + token):
        raise HTTPException(401, 'Invalid plugin credential')


app = FastAPI(title='MBSE Plugin API', version='0.1.0')
app.openapi_version = '3.0.3'
from .teamcenter_smw.router import router as smw_router
app.include_router(smw_router, dependencies=[Depends(authorize)])
from .cameo_mdk.router import router as cameo_router
app.include_router(cameo_router, dependencies=[Depends(authorize)])


class ImportRequest(BaseModel):
    profile: str = Field(pattern=r'^sysml-v[12]$')
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(max_length=14000000)
    job_id: str = 'semantic-source-validation'
    job_version: str = '1.0.0'
    source_system: str = 'mbse-plugin'


@app.get('/healthz')
def health():
    return {'status': 'ok'}


@app.get('/tools', dependencies=[Depends(authorize)])
def tools():
    from .registration import TOOLS
    return {'tools': [{'id': key, 'method': method, 'path': path, 'mutates': key == 'mbse.import'} for key, (method, path) in TOOLS.items()]}


@app.post('/imports', dependencies=[Depends(authorize)])
async def import_model(payload: ImportRequest):
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, 'Invalid base64') from exc
    if not content or len(content) > 10000000:
        raise HTTPException(413, 'Model must contain 1 to 10000000 bytes')
    base = os.getenv('DEPO_INGESTION_URL', '').rstrip('/')
    token = os.getenv('DEPO_INGESTION_TOKEN', '')
    if not base:
        raise HTTPException(503, 'DEPO_INGESTION_URL is not configured')
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    data = payload.model_dump(exclude={'content_base64', 'filename'})
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            response = await client.post(base + '/governed-import', headers=headers, data=data,
                files={'file': (Path(payload.filename).name, content, 'application/json' if payload.profile == 'sysml-v2' else 'application/xml')})
        if response.status_code >= 300:
            status = response.status_code if 400 <= response.status_code < 500 else 502
            raise HTTPException(status, f'Governed ingestion returned HTTP {response.status_code}')
        try:
            result = response.json()
        except ValueError as exc:
            raise HTTPException(502, 'Invalid ingestion response') from exc
        if not isinstance(result, dict):
            raise HTTPException(502, 'Invalid ingestion response')
        return result
    except httpx.HTTPError as exc:
        raise HTTPException(503, 'Governed ingestion unavailable') from exc


class Entity(BaseModel):
    id: str = Field(min_length=1)
    properties: dict = Field(default_factory=dict)
    ceim_type: str = 'Element'


class Relationship(BaseModel):
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relationship: str = ''


class GraphRequest(BaseModel):
    entities: list[Entity] = Field(max_length=2000)
    relationships: list[Relationship] = Field(default_factory=list, max_length=10000)


@app.post('/visualization', dependencies=[Depends(authorize)])
def graph(payload: GraphRequest):
    nodes = [{'id': e.id, 'label': str(e.properties.get('name') or e.id), 'type': e.ceim_type} for e in payload.entities]
    ids = {n['id'] for n in nodes}
    if len(ids) != len(nodes) or len(nodes) != len(payload.entities):
        raise HTTPException(422, 'Each entity requires a unique ID')
    edges = [{'source': r.source_id, 'target': r.target_id, 'label': r.relationship} for r in payload.relationships]
    if any(e['source'] not in ids or e['target'] not in ids for e in edges):
        raise HTTPException(422, 'Graph contains unresolved endpoints')
    return {'nodes': nodes, 'edges': edges}


@app.get('/', response_class=HTMLResponse)
def viewer():
    return Path(__file__).with_name('viewer.html').read_text(encoding='utf-8')
