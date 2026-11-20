"""OSLC Automation adapter over retained definitions and runs; no execution engine."""
from typing import Literal
from urllib.parse import quote
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from backend.mesh_store import PostgresRegistry
from backend.Services.oslc_service import OSLCService
from backend.depo_platform.authorization import graph_read_identity, approval_identity
from backend.depo_platform.service_urls import service_url
from backend.depo_platform.network import gateway_subscription_headers
from .representation import represent

AUTO='http://open-services.net/ns/auto#'
router=APIRouter(prefix='/oslc/automation',tags=['OSLC Automation adapter'])
KINDS={'plans':('data_job_definitions','AutomationPlan'),'requests':('data_job_runs','AutomationRequest'),'results':('data_job_runs','AutomationResult')}
PUBLIC=('job_id','job_version','version','workflow_number','run_number','source_name','source_system','source_standard','started_at','finished_at','replay_of')


def base():
    if not OSLCService.is_enabled():raise HTTPException(404,'OSLC integration is disabled')
    return OSLCService.config().base_url.rstrip('/')+'/oslc/automation'


def plan_identifier(record):
    job,version=record.get('job_id'),record.get('job_version') or record.get('version')
    return str(job)+':'+str(version) if job and version else None


def project(kind,record,root):
    identifier=plan_identifier(record) if kind=='plans' else record.get('run_id')
    plan_id=plan_identifier(record)
    if not identifier or not plan_id:return None
    uri=root+'/'+kind+'/'+quote(identifier,safe='')
    payload={'uri':uri,'type':'oslc_auto:'+KINDS[kind][1],'identifier':identifier,
        'title':str(record.get('name') or record.get('source_name') or record.get('job_id'))[:240],
        'resourceShape':root+'/shapes/'+kind,'evidence':{field:record[field] for field in PUBLIC if isinstance(record.get(field),(str,int,bool))},
        'publication_authorized':False}
    if kind=='plans':
        payload.update(definition_approval=record.get('lifecycle_state'),execution_enabled=record.get('lifecycle_state')=='approved' and record.get('enabled') is True,
            workspace='#/data-flow?view=pipelines&definition_id='+quote(record['job_id'],safe='')+'&definition_version='+quote(record['version'],safe=''))
        return payload
    status=record.get('status')
    state={'queued':'queued','running':'inProgress','completed':'complete','quality_warning':'complete','validation_failed':'complete','failed':'complete','timed_out':'complete','cancelled':'canceled'}.get(status,'new')
    verdict={'completed':'passed','quality_warning':'warning','validation_failed':'failed','failed':'error','timed_out':'error'}.get(status,'unavailable')
    # Execution success is separate from domain conformance and release approval.
    output=record.get('output_manifest') or {}
    if verdict=='passed' and isinstance(output,dict):
        validation=output.get('validation') or {}
        if isinstance(validation,dict) and validation.get('conforms') is False:verdict='failed'
    payload.update({'oslc_auto:state':'oslc_auto:'+state,'source_status':status,'workspace':'#/data-flow/'+quote(identifier,safe='')})
    plan_uri=root+'/plans/'+quote(plan_id,safe='')
    if kind=='requests':
        payload['oslc_auto:executesAutomationPlan']=plan_uri
        payload['result']=root+'/results/'+quote(identifier,safe='')
    else:
        payload.update({'oslc_auto:reportsOnAutomationPlan':plan_uri,'oslc_auto:producedByAutomationRequest':root+'/requests/'+quote(identifier,safe=''),'oslc_auto:verdict':'oslc_auto:'+verdict})
        counts=output.get('counts') if isinstance(output,dict) else None
        if isinstance(counts,dict):payload['counts']={key:value for key,value in counts.items() if isinstance(value,(int,float)) and not isinstance(value,bool)}
    return payload


@router.get('',dependencies=[Depends(graph_read_identity)])
def discovery(request:Request):
    root=base()
    return represent({'uri':root,'type':'oslc:ServiceProvider','title':'Nexus workflow automation',
        'services':[{'oslc:domain':AUTO,'queryCapabilities':[{'queryBase':root+'/'+kind,'resourceTypeUri':'oslc_auto:'+value[1],'resourceShape':root+'/shapes/'+kind} for kind,value in KINDS.items()],
            'creationFactories':[{'creation':root+'/requests','resourceTypeUri':'oslc_auto:AutomationRequest'}]}],
        'conformance_scope':'Retained-input execution adapter; not a claim of complete OSLC Automation conformance. CR/CO and publication authority remain with the native services.'},request)


@router.get('/shapes/{kind}',dependencies=[Depends(graph_read_identity)])
def shape(kind:Literal['plans','requests','results'],request:Request):
    root=base()
    return represent({'uri':root+'/shapes/'+kind,'type':'oslc:ResourceShape','describes':['oslc_auto:'+KINDS[kind][1]],
        'properties':[{'name':'identifier','propertyDefinition':'http://purl.org/dc/terms/identifier','occurs':'http://open-services.net/ns/core#Exactly-one','valueType':'http://www.w3.org/2001/XMLSchema#string','readOnly':True}]},request)


@router.get('/{kind}',dependencies=[Depends(graph_read_identity)])
def query(kind:Literal['plans','requests','results'],request:Request,limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0)):
    root=base()
    total,rows=PostgresRegistry(KINDS[kind][0]).page(limit=limit,offset=offset,exclude_latest=True)
    members=[value for record in rows if isinstance(record,dict) and (value:=project(kind,record,root)) is not None]
    return represent({'uri':root+'/'+kind,'type':'oslc:QueryResult','members':members,'total':total,
        'nextPage':root+'/'+kind+'?limit='+str(limit)+'&offset='+str(offset+limit) if offset+limit<total else None},request)


@router.get('/{kind}/{identifier}',dependencies=[Depends(graph_read_identity)])
def resource(kind:Literal['plans','requests','results'],identifier:str,request:Request):
    root=base()
    if len(identifier)>200:raise HTTPException(404,'Automation resource not found')
    record=PostgresRegistry(KINDS[kind][0]).get(identifier)
    payload=project(kind,record,root) if isinstance(record,dict) else None
    if not payload or payload['identifier']!=identifier:raise HTTPException(404,'Automation resource not found')
    return represent(payload,request)


class Submission(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    job_id:str=Field(pattern=r'^[a-z][a-z0-9-]{2,62}$')
    version:str=Field(pattern=r'^[0-9]+\.[0-9]+\.[0-9]+$')
    replay_run_id:str=Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9._:-]+$')
    idempotency_key:str=Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9._:-]+$')


@router.post('/requests',status_code=202)
def submit(payload:Submission,request:Request):
    root=base()
    actor=approval_identity(request,{},token_env='DATA_JOB_EXECUTION_TOKEN')
    from .media import negotiate
    if negotiate(request.headers.get('accept','application/json')) is None:raise HTTPException(406,'No supported OSLC representation is acceptable')
    if request.headers.get('configuration-context'):raise HTTPException(422,'Retained-input replay uses its original baseline; select a run with the intended configuration')
    prior=PostgresRegistry('data_job_runs').get(payload.replay_run_id)
    if not prior:raise HTTPException(404,'Retained input run not found')
    if prior.get('job_id')!=payload.job_id or prior.get('job_version')!=payload.version:raise HTTPException(409,'Retained input does not belong to the selected plan version')
    endpoint=service_url('DATA_PIPELINE_SERVICE_URL','http://127.0.0.1:8019/api/v1').rstrip('/')
    if not endpoint.endswith('/api/v1'):endpoint+='/api/v1'
    endpoint+='/pipeline/jobs/runs/'+quote(payload.replay_run_id,safe='')+'/replay'
    if os.getenv('AUTH_MODE','token').lower()=='entra':
        from backend.agentic_service.transport_auth import downstream_headers
        headers=downstream_headers(request,endpoint)
    else:
        headers=gateway_subscription_headers(endpoint)
        for name in ('authorization','x-api-key'):
            if request.headers.get(name):headers[name]=request.headers[name]
    for name in ('x-request-id',):
        if request.headers.get(name):headers[name]=request.headers[name]
    try:
        with httpx.Client(timeout=20,trust_env=False,follow_redirects=False) as client:
            response=client.post(endpoint,headers=headers,json={'idempotency_key':payload.idempotency_key})
        if response.status_code>=400:
            raise HTTPException(response.status_code if response.status_code in {401,403,404,409,422} else 503,'Native execution did not confirm the request. Inspect retained runs before retrying the same submission reference.')
        native=response.json()
        run=native.get('run_manifest') if isinstance(native,dict) else None
        if not isinstance(run,dict) or run.get('replay_of')!=payload.replay_run_id or run.get('executed_by')!=actor or plan_identifier(run)!=payload.job_id+':'+payload.version:
            raise HTTPException(503,'Native execution returned an unverified run identity; reconcile before retrying')
        result=project('requests',run,root)
        if not result:raise HTTPException(503,'Native execution did not return a retained request')
        represented=represent(result,request)
        represented.status_code=202
        represented.headers['Location']=result['uri']
        return represented
    except httpx.TimeoutException:
        raise HTTPException(504,'Execution outcome is unverified. Inspect retained runs; keep the same submission reference.') from None
    except (httpx.HTTPError,ValueError,TypeError):
        raise HTTPException(503,'Native execution is unavailable; reconcile retained runs before retrying') from None
