"""Workflow maintenance requests; native CAS execution under the shared CR/CO matrix."""
from copy import deepcopy
from uuid import UUID
from fastapi import HTTPException
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.bridge_contract import digest
from backend.depo_platform.change_requests import event, REVIEW_ACTIONS
from backend.depo_platform.approval_matrix import order_valid as matrix_valid
from . import job_definitions, run_records

store = PostgresRegistry('data_job_definition_changes_v1')
OPERATIONS = {'approve','disable','schedule','clear','revise'}
SCHEMA = 'nexus.workflow-definition-change.v1'


def load(identifier):
    record = store.get(identifier)
    if not record: raise HTTPException(404,'Workflow change request was not found')
    return record


def prepare(job_id, version, operation, parameters):
    if operation not in OPERATIONS: raise HTTPException(422,'Unsupported workflow maintenance operation')
    record = job_definitions.get(job_id,version)
    if not record: raise HTTPException(404,'Workflow version was not found')
    if not isinstance(parameters,dict): raise HTTPException(422,'Workflow parameters must be an object')
    allowed={'interval_seconds','replay_run_id','retry_policy'} if operation=='schedule' else {'version','allowed_standards'} if operation=='revise' else set()
    if set(parameters)-allowed: raise HTTPException(422,'Unexpected workflow maintenance parameters')
    try: job_definitions.reviewed_update(record,operation,parameters,'validation-only')
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    if operation=='revise' and job_definitions.get(job_id,parameters['version']) is not None:
        raise HTTPException(409,'Target workflow version already exists; select a newer version')
    plan={'schema':SCHEMA,'job_id':job_id,'version':version,'operation':operation,
          'definition_sha256':digest(record),'parameters':deepcopy(parameters)}
    if operation=='schedule':
        replay=run_records.get(parameters.get('replay_run_id',''))
        if not replay or replay.get('job_id')!=job_id or replay.get('job_version')!=version:
            raise HTTPException(422,'Select a retained input run of this exact workflow version')
        plan['replay_input_sha256']=digest(replay.get('input_manifest') or {})
    return record,plan,digest(plan)


def require_actor(actor):
    if not isinstance(actor,str) or not actor.strip():
        raise HTTPException(403,'An authenticated workflow approver is required')


def valid_order(record):
    change=record['change_request']; order=change.get('order') or {}
    return ((change.get('plan') or {}).get('schema')==SCHEMA and matrix_valid(change) and digest(change.get('plan'))==change.get('plan_digest')
            and change.get('request_id')==record['request_id'] and change.get('state') in {'authorized','executed'}
            and order.get('order_id')==record['request_id'] and order.get('plan_digest')==change['plan_digest']
            and order.get('operation')=='maintain_workflow_definition' and bool(order.get('authorized_by')))


def view(identifier):
    record=load(identifier);change=record['change_request']
    current=job_definitions.get(record['job_id'],record['version'])
    applied=change['state']=='executed'
    if applied:
        if record['operation']=='revise':current=job_definitions.get(record['job_id'],record['parameters']['version'])
        checksum=change['plan_digest'];changed=not current or digest(current)!=(record.get('receipt') or {}).get('definition_sha256')
    else:
        try: _,_,checksum=prepare(record['job_id'],record['version'],record['operation'],record['parameters']);changed=checksum!=change['plan_digest']
        except HTTPException: checksum=change['plan_digest'];changed=True
    return {'preview_id':identifier,'current_plan_digest':checksum,'change_request':deepcopy(change),
            'scope_changed':changed,'already_applied':applied,'authorization_valid':valid_order(record) and not changed,
            'job_id':record['job_id'],'version':record['version'],'operation':record['operation'],
            'scope':'Maintain only the retained workflow definition and reviewed schedule. No data is published.',
            'receipt':deepcopy(record.get('receipt'))}


def save(identifier,record):
    record['updated_at']=job_definitions.now()
    from backend.depo_platform.resource_identity import ensure
    if isinstance(store,PostgresRegistry): ensure(record['change_request'],'workflow_changes',identifier)
    return store.put(identifier,record)


def submit(payload,actor):
    require_actor(actor)
    identifier=payload.request_id
    try: UUID(identifier)
    except (ValueError,TypeError): raise HTTPException(422,'A UUID request identity is required')
    if not payload.reason.strip(): raise HTTPException(422,'Provide the reason for this workflow change')
    with store.advisory_lock(identifier) as acquired:
        if acquired is False: raise HTTPException(409,'Workflow request is being updated')
        definition,plan,checksum=prepare(payload.job_id,payload.version,payload.operation,payload.parameters)
        old=store.get(identifier)
        if old:
            if old['change_request']['plan_digest']!=checksum or old['change_request']['requested_by']!=actor:
                raise HTTPException(409,'Request identity already belongs to another scope or requester')
            return view(identifier)
        change={'request_id':identifier,'revision':0,'state':'submitted','plan_digest':checksum,
                'plan':plan,'requested_by':actor,'reason':payload.reason,'order':None,'history':[]}
        event(change,'submit',actor,payload.reason)
        record={'request_id':identifier,'job_id':payload.job_id,'version':payload.version,'operation':payload.operation,
                'parameters':deepcopy(payload.parameters),'name':definition['name'],'status':'submitted',
                'created_at':job_definitions.now(),'change_request':change}
        from backend.depo_platform.resource_identity import ensure
        if isinstance(store,PostgresRegistry): ensure(change,'workflow_changes',identifier)
        store.create(identifier,record)
        return view(identifier)


def command(identifier,payload,actor):
    require_actor(actor)
    with store.advisory_lock(identifier) as acquired:
        if acquired is False: raise HTTPException(409,'Workflow request is being updated')
        record=load(identifier);before=deepcopy(record);change=record['change_request']
        if payload.action=='execute' and change['state']=='executed':
            result=view(identifier)
            if payload.expected_plan_digest!=change['plan_digest'] or not result['authorization_valid']:
                raise HTTPException(409,'Executed workflow receipt does not match the retained scope')
            return result
        if payload.action in {'reject','cancel'}:
            checksum=change['plan_digest']
            definition=None
        else:
            definition,_,checksum=prepare(record['job_id'],record['version'],record['operation'],record['parameters'])
        if payload.expected_revision!=change['revision'] or payload.expected_plan_digest!=checksum or checksum!=change['plan_digest']:
            raise HTTPException(409,'Workflow definition or request changed; prepare a new request')
        if payload.action=='execute':
            if not valid_order(record) or change['state']!='authorized': raise HTTPException(409,'An exact authorized CO is required')
            updated=job_definitions.reviewed_update(definition,record['operation'],record['parameters'],actor)
            change['state']='executed';event(change,'execute',actor,payload.reason)
            record.update(status='executed',updated_at=job_definitions.now(),
                          receipt={'definition_sha256':digest(updated),'operation':record['operation'],'executed_by':actor,'version':updated['version']})
            key=job_definitions.key(record['job_id'],record['version'])
            expected_rows={key:definition};updated_rows={key:updated}
            if record['operation']=='revise':
                target=job_definitions.key(record['job_id'],updated['version'])
                expected_rows[target]=None;updated_rows={key:definition,target:updated}
            if not store.transition_bundle(identifier,record,related_store=job_definitions.store,
                    expected_rows=expected_rows,updated_rows=updated_rows,expected_value=before):
                raise HTTPException(409,'Workflow changed concurrently; no maintenance result was committed')
            return view(identifier)
        if payload.action not in REVIEW_ACTIONS or change['state'] not in REVIEW_ACTIONS[payload.action]:
            raise HTTPException(409,'Decision is not allowed in the current request state')
        if payload.action=='reject' and not payload.reason.strip(): raise HTTPException(422,'Provide a return reason')
        change['state']={'accept':'accepted','reject':'rejected','authorize':'authorized','cancel':'cancelled'}[payload.action]
        if payload.action=='authorize':change['order']={'order_id':identifier,'plan_digest':checksum,
                    'operation':'maintain_workflow_definition','authorized_by':actor}
        event(change,payload.action,actor,payload.reason);record['status']=change['state'];save(identifier,record)
        return view(identifier)


def execute_legacy(job_id,version,operation,parameters,payload,actor):
    require_actor(actor)
    identifier=payload.get('change_request_id')
    if not isinstance(identifier,str):raise HTTPException(409,'Submit and authorize this workflow change in Change Control first')
    record=load(identifier)
    if (record['job_id'],record['version'],record['operation'],record['parameters'])!=(job_id,version,operation,parameters):
        raise HTTPException(409,'CO does not authorize this workflow maintenance scope')
    from backend.depo_platform.request_bodies import MergeChangeCommand
    current=view(identifier)
    command(identifier,MergeChangeCommand(action='execute',expected_revision=current['change_request']['revision'],
            expected_plan_digest=current['current_plan_digest']),actor)
    return job_definitions.get(job_id,version)
