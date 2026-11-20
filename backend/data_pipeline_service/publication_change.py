"""Exact retained-partition approval; canonical publication keeps execution ownership."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import json
import re
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from backend.artifact_store import ArtifactStore
from backend.depo_platform.bridge_contract import digest
from backend.depo_platform.change_requests import event, REVIEW_ACTIONS
from . import run_records
from .publication_scope import publication_scope

PLAN_SCHEMA='nexus.native-pipeline-publication.v1'
PARAMETERS=('ontology_id','prefix','semantic_release','source_system')


@asynccontextmanager
async def publication_lock(run_id):
    """Keep connection acquisition/release off the event loop; cancellation cannot leak a lock."""
    lock=run_records.store.advisory_lock('publish:'+run_id)
    entering=asyncio.create_task(run_in_threadpool(lock.__enter__))
    try:
        acquired=await asyncio.shield(entering)
    except asyncio.CancelledError:
        await entering
        await run_in_threadpool(lock.__exit__,None,None,None)
        raise
    try:yield acquired
    finally:await run_in_threadpool(lock.__exit__,None,None,None)

SEMANTIC_JOBS={'normalize-ceim','validate-semantic-batch','normalize-unstructured-ceim','connector-ceim-normalize'}


def load(run_id):
    record=run_records.get(run_id)
    if not record:raise HTTPException(404,'Data job run was not found')
    return record


def accepted_partition(record):
    if record.get('status')!='completed' or record.get('job_type') not in SEMANTIC_JOBS:
        raise HTTPException(409,'Only a completed semantic batch can enter publication review')
    output=record.get('output_manifest') or {}
    artifact=(output.get('partition_artifacts') or {}).get('accepted')
    try:
        metadata,path=ArtifactStore().resolve(artifact)
        if metadata.get('kind')!='accepted-semantic-partition':raise ValueError('Wrong partition kind')
        content=path.read_bytes();batch=json.loads(content)
        if not isinstance(batch,dict):raise ValueError('Partition must be an object')
    except (ValueError,OSError,TypeError) as exc:
        raise HTTPException(409,'The retained accepted partition must be restored and validated before review') from exc
    return artifact,content,batch


def prepare(record,parameters):
    artifact,content,batch=accepted_partition(record)
    intent={'ontology_id':publication_scope(parameters,record,batch),'prefix':parameters.get('prefix','ceim'),
        'semantic_release':parameters.get('semantic_release'),
        'source_system':parameters.get('source_system') or batch.get('source_system') or record.get('source_system'),
        'batch_digest':run_records._digest(batch)}
    if not isinstance(intent['semantic_release'],dict) or not intent['semantic_release'].get('asset_id') or not intent['semantic_release'].get('version'):
        raise HTTPException(422,'Select the approved semantic release before submitting publication review')
    plan={'run_id':record['run_id'],'job_id':record.get('job_id'),'job_version':record.get('job_version'),
        'input_digest':(record.get('input_manifest') or {}).get('payload_digest'),
        'partition_artifact_id':artifact,'partition_sha256':hashlib.sha256(content).hexdigest(),'intent':intent}
    return plan,digest(plan)


def valid_order(record):
    change=record.get('change_request');order=change.get('order') if isinstance(change,dict) else None
    plan=change.get('plan_digest') if isinstance(change,dict) else None
    from backend.depo_platform.approval_matrix import order_valid as matrix_order_valid
    return (matrix_order_valid(change) and isinstance(order,dict) and isinstance(plan,str) and re.fullmatch('[0-9a-f]{64}',plan) is not None
        and change.get('request_id')==record.get('run_id') and digest(change.get('plan'))==plan
        and change.get('state') in {'authorized','executing','needs_recovery','executed'}
        and order.get('order_id')==record.get('run_id') and order.get('plan_digest')==plan
        and order.get('operation')=='publish_accepted_partition' and order.get('publish') is True
        and isinstance(order.get('authorized_by'),str) and bool(order['authorized_by'].strip()))


def save(record):
    record['change_request']['updated_at']=record['change_request']['history'][-1]['at']
    from backend.mesh_store import PostgresRegistry
    if isinstance(run_records.store,PostgresRegistry):
        from backend.oslc_service.notifications import retain_native_change
        return retain_native_change(run_records.store,record['run_id'],record,'pipeline',record['run_id'])
    return run_records.store.put(record['run_id'],record)


async def view(run_id):
    record=await run_in_threadpool(load,run_id);change=record.get('change_request')
    if not isinstance(change,dict):raise HTTPException(404,'No publication review request has been submitted for this run')
    _,current=await run_in_threadpool(prepare,record,change['parameters'])
    return {'preview_id':run_id,'run_id':run_id,'current_plan_digest':current,'plan_schema':PLAN_SCHEMA,
        'change_request':deepcopy(change),'scope_changed':current!=change['plan_digest'],'already_applied':False,
        'authorization_valid':valid_order(record) and current==change['plan_digest'],
        'scope':'Publish only this retained accepted partition into the selected graph scope',
        'intent':change['plan']['intent'],'partition_sha256':change['plan']['partition_sha256']}


async def submit(run_id,parameters,reason,actor):
    if not isinstance(actor,str) or not actor.strip():raise HTTPException(403,'Verified publication approval access is required')
    if not reason.strip():raise HTTPException(422,'Provide the business reason for publication review')
    parameters={key:deepcopy(parameters[key]) for key in PARAMETERS if key in parameters}
    async with publication_lock(run_id) as acquired:
        if not acquired:raise HTTPException(409,'Run publication is active; refresh retained status')
        record=await run_in_threadpool(load,run_id);plan,checksum=await run_in_threadpool(prepare,record,parameters)
        previous=record.get('change_request')
        if previous:
            if previous.get('plan_digest')!=checksum:raise HTTPException(409,'This run has a different retained request; prepare a new run for changed scope')
            return await view(run_id)
        output=record.get('output_manifest') or {}
        if output.get('publication') or output.get('publication_intent'):
            raise HTTPException(409,'An attempted publication cannot be retroactively approved; reconcile its existing receipt')
        change={'request_id':run_id,'revision':0,'state':'submitted','plan_digest':checksum,'plan':plan,
            'parameters':parameters,'requested_by':actor,'reason':reason,'order':None,'history':[]}
        await run_in_threadpool(event,change,'submit',actor,reason);record['change_request']=change
        await run_in_threadpool(save,record)
        return await view(run_id)


from backend.depo_platform.release_chain import guarded as release_guard

@release_guard(lambda run_id,*args,**kwargs:('pipeline',run_id,run_records.store))
async def execute_locked(run_id,parameters,request,actor):
    from .router import _publish_job_run_locked
    record=await run_in_threadpool(load,run_id);change=record.get('change_request')
    if not change:
        raise HTTPException(409,'Submit and authorize a Change Control request before publication. Read retained receipts to inspect historical publications.')
    _,checksum=await run_in_threadpool(prepare,record,parameters)
    if not valid_order(record) or change['plan_digest']!=checksum:
        raise HTTPException(409,'The exact retained partition and destination require valid authorization')
    if change['state']!='authorized':raise HTTPException(409,'Verify the retained publication receipt; do not replay the write')
    change['state']='executing';event(change,'execute',actor);await run_in_threadpool(save,record)
    try:
        await _publish_job_run_locked(run_id,change['parameters'],request,actor)
        return await reconcile_locked(run_id,actor)
    except Exception:
        latest=await run_in_threadpool(load,run_id)
        latest['change_request']['state']='needs_recovery';event(latest['change_request'],'execution_unverified',actor)
        await run_in_threadpool(save,latest)
        raise


async def reconcile_locked(run_id,actor):
    from .router import _reconcile_graph_publication
    record=await run_in_threadpool(load,run_id);change=record['change_request']
    if change['state'] not in {'executing','needs_recovery'} or not valid_order(record):
        raise HTTPException(409,'No authorized publication is awaiting receipt verification')
    _,checksum=await run_in_threadpool(prepare,record,change['parameters'])
    output=record.get('output_manifest') or {};intent=change['plan']['intent']
    if checksum!=change['plan_digest'] or output.get('publication_intent')!=intent:
        raise HTTPException(409,'Retained partition or attempted destination changed; publication is not verified')
    receipt=await _reconcile_graph_publication(ontology_id=intent['ontology_id'],publication_id=run_id,headers={},timeout_seconds=15)
    if (not isinstance(receipt,dict) or receipt.get('status')!='published' or receipt.get('current') is not True
        or receipt.get('ontology_id')!=intent['ontology_id'] or receipt.get('publication_id')!=run_id
        or any(type(receipt.get(key)) is not int or receipt[key]<0 for key in ('resources','relationships'))):
        raise HTTPException(409,'No exact current graph receipt is verified; no publication was replayed')
    if not output.get('publication'):
        record=await run_in_threadpool(run_records.publication_succeeded,record,{
            'status':'published','ontology_id':intent['ontology_id'],'publication_id':run_id,'publication':receipt,'reconciled_by':actor})
    publication=record['output_manifest']['publication']
    if publication.get('ontology_id')!=intent['ontology_id'] or publication.get('publication_id')!=run_id or publication.get('status')!='published' or record['output_manifest'].get('publication_digest')!=run_records._digest(publication):
        raise HTTPException(409,'Retained publication evidence does not match this run')
    change=record['change_request'];change['state']='executed'
    change['receipt']={'ontology_id':intent['ontology_id'],'publication_id':run_id,'current':True,'verified_by':actor}
    event(change,'verify_graph_receipt',actor);await run_in_threadpool(save,record)
    return await view(run_id)


async def command(run_id,payload,request,actor):
    if not isinstance(actor,str) or not actor.strip():raise HTTPException(403,'Verified publication approval access is required')
    async with publication_lock(run_id) as acquired:
        if not acquired:raise HTTPException(409,'Run publication is active; refresh retained status')
        record=await run_in_threadpool(load,run_id);change=record.get('change_request')
        if not change:raise HTTPException(404,'No publication review request is retained')
        _,checksum=await run_in_threadpool(prepare,record,change['parameters'])
        if payload.expected_revision!=change['revision'] or payload.expected_plan_digest!=checksum or checksum!=change['plan_digest']:
            raise HTTPException(409,'Request revision or retained partition scope changed; refresh before deciding')
        if payload.action=='execute':return await execute_locked(run_id,change['parameters'],request,actor)
        if payload.action=='reconcile':return await reconcile_locked(run_id,actor)
        if payload.action not in REVIEW_ACTIONS or change['state'] not in REVIEW_ACTIONS[payload.action]:
            raise HTTPException(409,'This decision is not allowed in the current request state')
        if payload.action=='reject' and not payload.reason.strip():raise HTTPException(422,'Provide a reason for returning the request')
        change['state']={'accept':'accepted','reject':'rejected','authorize':'authorized','cancel':'cancelled'}[payload.action]
        if payload.action=='authorize':change['order']={'order_id':run_id,'plan_digest':checksum,'operation':'publish_accepted_partition','publish':True,'authorized_by':actor}
        event(change,payload.action,actor,payload.reason);await run_in_threadpool(save,record)
        return await view(run_id)
