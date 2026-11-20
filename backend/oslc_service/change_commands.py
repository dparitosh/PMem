"""Central routing to native merge CR/CO commands; no second approval database."""
from urllib.parse import quote
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.depo_platform.request_bodies import MergeChangeCommand, BridgeChangeCommand, ProductChangeCommand, PipelineChangeCommand
from backend.depo_platform.authorization import graph_read_identity, approval_identity
from backend.depo_platform.service_urls import service_url
from backend.depo_platform.network import gateway_subscription_headers

router=APIRouter(tags=['Change request and native release commands'])

def native_request(request, preview_id, payload=None, source='merges'):
    if source=='merges':
        root=service_url('ONTOLOGY_SERVICE_URL','http://127.0.0.1:8011/api/v1').rstrip('/')
        path='/ontologies/merges/'
    elif source=='bridges':
        root=service_url('AGENTIC_SERVICE_URL','http://127.0.0.1:8012/api/v1').rstrip('/')
        path='/workflows/bridge/previews/'
    elif source=='product_changes':
        root=service_url('DATA_PRODUCT_SERVICE_URL','http://127.0.0.1:8017/api/v1').rstrip('/')
        path='/data-products/change-requests/'
    elif source=='publications':
        root=service_url('ONTOLOGY_SERVICE_URL','http://127.0.0.1:8011/api/v1').rstrip('/')
        path='/ontologies/'
    elif source=='workflow_changes':
        root=service_url('DATA_PIPELINE_SERVICE_URL','http://127.0.0.1:8019/api/v1').rstrip('/')
        path='/pipeline/jobs/definition-changes/'
    elif source=='import_changes':
        root=service_url('INGESTION_SERVICE_URL','http://127.0.0.1:8014/api/v1').rstrip('/')
        path='/import/'
    elif source=='pipeline':
        root=service_url('DATA_PIPELINE_SERVICE_URL','http://127.0.0.1:8019/api/v1').rstrip('/')
        path='/pipeline/jobs/runs/'
    else:raise HTTPException(404,'Unknown native change source')
    if not root.endswith('/api/v1'):root+='/api/v1'
    endpoint=root+path+quote(preview_id,safe='')+('' if source=='product_changes' else '/change')
    if os.getenv('AUTH_MODE','token').lower()=='entra':
        from backend.agentic_service.transport_auth import downstream_headers
        headers=downstream_headers(request,endpoint,graph_read=payload is None)
    else:
        bearer=request.headers.get('authorization','')
        key=request.headers.get('x-api-key','')
        headers={**gateway_subscription_headers(endpoint),**({'Authorization':bearer} if bearer else {'X-API-Key':key})}
    try:
        with httpx.Client(timeout=180 if payload and payload.action=='execute' else 20,trust_env=False,follow_redirects=False) as client:
            response=client.request('POST' if payload else 'GET',endpoint,headers=headers,
                **({'json':payload.model_dump()} if payload else {}))
        if response.status_code>=400:
            detail=None
            if response.status_code<500:
                try:
                    error=response.json()
                except ValueError:
                    error=None
                if isinstance(error,dict): detail=error.get('detail')
            raise HTTPException(response.status_code if response.status_code in {401,403,404,409,422} else 503,
                detail[:500] if isinstance(detail,str) else 'Native owning service could not confirm this action; inspect retained status before retrying')
        result=response.json()
        if not isinstance(result,dict) or result.get('preview_id')!=preview_id:
            raise ValueError('Native change identity mismatch')
        return result
    except httpx.TimeoutException:
        raise HTTPException(504,'The action outcome is unverified. Refresh the retained request and verify its native receipt; do not replay the write') from None
    except (httpx.HTTPError,ValueError):
        raise HTTPException(503,'Native change service is unavailable or returned invalid evidence. Refresh retained status before any new command') from None

@router.get('/api/v1/change-control/merges/{preview_id}/request',dependencies=[Depends(graph_read_identity)])
def merge_request_status(preview_id: str,request: Request):
    return native_request(request,preview_id)

@router.post('/api/v1/change-control/merges/{preview_id}/request')
def merge_request_command(preview_id: str,payload: MergeChangeCommand,request: Request):
    approval_identity(request,{},token_env='ONTOLOGY_APPROVAL_TOKEN')
    return native_request(request,preview_id,payload)


@router.get('/api/v1/change-control/bridges/{preview_id}/request',dependencies=[Depends(graph_read_identity)])
def mapping_request_status(preview_id: str,request: Request):
    return native_request(request,preview_id,source='bridges')

@router.post('/api/v1/change-control/bridges/{preview_id}/request')
def mapping_request_command(preview_id: str,payload: BridgeChangeCommand,request: Request):
    approval_identity(request,{},token_env='AGENTIC_APPROVAL_TOKEN')
    return native_request(request,preview_id,payload,source='bridges')


@router.get('/api/v1/change-control/product_changes/{product_version}/request',dependencies=[Depends(graph_read_identity)])
def product_request_status(product_version: str,request: Request):
    return native_request(request,product_version,source='product_changes')

@router.post('/api/v1/change-control/product_changes/{product_version}/request')
def product_request_command(product_version: str,payload: ProductChangeCommand,request: Request):
    approval_identity(request,{},token_env='DATA_PRODUCT_APPROVAL_TOKEN')
    return native_request(request,product_version,payload,source='product_changes')


@router.get('/api/v1/change-control/pipeline/{run_id}/request',dependencies=[Depends(graph_read_identity)])
def pipeline_request_status(run_id: str,request: Request):
    return native_request(request,run_id,source='pipeline')


@router.post('/api/v1/change-control/pipeline/{run_id}/request')
def pipeline_request_command(run_id: str,payload: PipelineChangeCommand,request: Request):
    approval_identity(request,{},token_env='CEIM_PUBLISH_APPROVAL_TOKEN')
    return native_request(request,run_id,payload,source='pipeline')


@router.get('/api/v1/change-control/publications/{ontology_id}/request',dependencies=[Depends(graph_read_identity)])
def ontology_request_status(ontology_id: str,request: Request):
    return native_request(request,ontology_id,source='publications')


@router.post('/api/v1/change-control/publications/{ontology_id}/request')
def ontology_request_command(ontology_id: str,payload: MergeChangeCommand,request: Request):
    approval_identity(request,{},token_env='ONTOLOGY_APPROVAL_TOKEN')
    return native_request(request,ontology_id,payload,source='publications')


@router.get('/api/v1/change-control/workflow_changes/{identifier}/request',dependencies=[Depends(graph_read_identity)])
def workflow_change_status(identifier: str,request: Request):
    return native_request(request,identifier,source='workflow_changes')

@router.post('/api/v1/change-control/workflow_changes/{identifier}/request')
def workflow_change_command(identifier: str,payload: MergeChangeCommand,request: Request):
    approval_identity(request,{},token_env='DATA_JOB_APPROVAL_TOKEN')
    return native_request(request,identifier,payload,source='workflow_changes')


@router.get('/api/v1/change-control/import_changes/{identifier}/request',dependencies=[Depends(graph_read_identity)])
def import_change_status(identifier: str,request: Request):
    return native_request(request,identifier,source='import_changes')

@router.post('/api/v1/change-control/import_changes/{identifier}/request')
def import_change_command(identifier: str,payload: MergeChangeCommand,request: Request):
    approval_identity(request,{},token_env='INGESTION_WRITE_TOKEN')
    return native_request(request,identifier,payload,source='import_changes')
