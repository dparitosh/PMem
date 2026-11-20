"""CR/CO adapter for the retained importer; no alternate graph writer."""
from copy import deepcopy
import re
from datetime import datetime,timezone
from fastapi import HTTPException
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.bridge_contract import digest
from backend.depo_platform.change_requests import event, REVIEW_ACTIONS
from backend.depo_platform.approval_matrix import order_valid
from backend.oslc_service.notifications import retain_native_change

store=PostgresRegistry('tracked_import_changes_v1')
SCHEMA='nexus.tracked-import-load.v1'


def service():
    from backend.Services.unified_data_import import UnifiedDataImportService
    return UnifiedDataImportService


def snapshot(task_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',task_id):raise HTTPException(422,'Invalid import identity')
    task=service()._read_status_task(task_id)
    if not task:raise HTTPException(404,'Import task was not found')
    if task.get('status')!='ready_for_commit' or task.get('committing'):
        raise HTTPException(409,'Import is not ready for a reviewed graph load')
    from backend.Services.import_task_persistence import retained_rows
    try:rows=retained_rows(task,service()._task_snapshot_path(task_id))
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    if not isinstance(rows,list) or not rows:raise HTTPException(409,'Complete retained import rows are required')
    plan={'schema':SCHEMA,'task_id':task_id,'filename':task.get('filename'),
          'rows_sha256':digest(rows),'row_count':len(rows),'schema_sha256':digest(task.get('auto_schema') or {}),
          'source_metadata_sha256':digest({key:task.get(key) for key in ('stats','file_type','parse_options')}),'workflow_id':task.get('workflow_id')}
    return plan,digest(plan)


def valid(record):
    change=record.get('change_request') or {};plan=change.get('plan') or {};order=change.get('order') or {}
    return (change.get('state') in {'authorized','executing','executed','needs_recovery'} and plan.get('schema')==SCHEMA and plan.get('task_id')==record.get('task_id')
        and change.get('request_id')==record.get('task_id') and digest(plan)==change.get('plan_digest')
        and order.get('order_id')==record.get('task_id') and order.get('plan_digest')==change.get('plan_digest')
        and order.get('operation')=='load_retained_import' and bool(order.get('authorized_by')) and order_valid(change))


def load(task_id):
    record=store.get(task_id)
    if not record:raise HTTPException(404,'Import change request was not found')
    return record


def save(task_id,record):
    record['updated_at']=datetime.now(timezone.utc).isoformat()
    if not isinstance(store,PostgresRegistry):return store.put(task_id,deepcopy(record))
    return retain_native_change(store,task_id,record,'import_changes',task_id)


def view(task_id):
    record=load(task_id);change=record['change_request'];state=change['state']
    changed=False
    if state not in {'executing','executed','needs_recovery'}:
        try:_,current=snapshot(task_id);changed=current!=change['plan_digest']
        except HTTPException:changed=True
    task=service().get_status(task_id) or {}
    if state=='executed':
        receipt=record.get('receipt') or {}
        changed=(task.get('status')!='completed' or (service()._read_status_task(task_id) or {}).get('load_change_digest')!=change['plan_digest']
            or receipt.get('plan_digest')!=change['plan_digest'] or digest(task.get('result'))!=digest(receipt.get('result')))
    return {'preview_id':task_id,'task_id':task_id,'filename':record['name'],
        'current_plan_digest':change['plan_digest'],'scope_changed':changed,'already_applied':state=='executed',
        'authorization_valid':valid(record) and not changed,'change_request':deepcopy(change),
        'scope':'Load this exact retained import. Ontology mapping publication remains separately governed.',
        'receipt':record.get('receipt'),'task_status':task.get('status')}


def submit(task_id,actor,reason):
    if not isinstance(actor,str) or not actor.strip():raise HTTPException(403,'Authenticated approver required')
    with store.advisory_lock(task_id) as acquired:
        if acquired is False:raise HTTPException(409,'Import change is busy')
        old=store.get(task_id)
        if old:return view(task_id)
        plan,checksum=snapshot(task_id)
        change={'request_id':task_id,'revision':0,'state':'submitted','plan':plan,'plan_digest':checksum,
                'requested_by':actor,'reason':reason or 'Load retained engineering records','order':None,'history':[]}
        event(change,'submit',actor,change['reason'])
        save(task_id,{'task_id':task_id,'name':plan['filename'],'change_request':change})
        return view(task_id)


def require_dispatch(task_id,task,config):
    """Revalidate the exact CO immediately before queuing and before graph work."""
    record=load(task_id);change=record['change_request'];plan=change['plan']
    if change['state']!='executing' or not valid(record):raise ValueError('An exact executing import CO is required')
    if (task.get('load_change_digest')!=change['plan_digest'] or digest(task.get('parsed_rows'))!=plan['rows_sha256']
        or digest(config)!=plan['schema_sha256'] or digest({key:task.get(key) for key in ('stats','file_type','parse_options')})!=plan['source_metadata_sha256']
        or task.get('workflow_id')!=plan.get('workflow_id')):
        raise ValueError('Retained import or CO scope changed; no new graph dispatch is allowed')


async def command(task_id,payload,actor):
    if not isinstance(actor,str) or not actor.strip():raise HTTPException(403,'Authenticated approver required')
    with store.advisory_lock(task_id) as acquired:
        if acquired is False:raise HTTPException(409,'Import change is busy')
        record=load(task_id);change=record['change_request'];action=payload.action
        if payload.expected_revision!=change['revision'] or payload.expected_plan_digest!=change['plan_digest']:
            raise HTTPException(409,'Import request changed; refresh its retained evidence')
        if action=='reconcile':
            if change['state'] not in {'executing','needs_recovery'}:raise HTTPException(409,'No dispatched load to reconcile')
            task=service()._read_status_task(task_id) or {}
            if task.get('load_change_digest')!=change['plan_digest']:raise HTTPException(409,'Native load scope does not match the CO')
            if task.get('status')=='completed' and not task.get('committing') and task.get('result') and not task['result'].get('incomplete_relationships') and not task['result'].get('relationships_skipped'):
                change['state']='executed';record['receipt']={'task_id':task_id,'plan_digest':change['plan_digest'],'result':deepcopy(task['result'])}
            elif task.get('status')=='outcome_unknown':change['state']='needs_recovery'
            else:return view(task_id)
            event(change,'reconcile',actor,payload.reason);save(task_id,record);return view(task_id)
        if action in REVIEW_ACTIONS and change['state'] in REVIEW_ACTIONS[action]:
            if action not in {'cancel','reject'}:
                _,checksum=snapshot(task_id)
                if checksum!=change['plan_digest']:raise HTTPException(409,'Import scope changed; review a new source baseline')
            if action=='reject' and not payload.reason.strip():raise HTTPException(422,'Provide a return reason')
            change['state']={'accept':'accepted','authorize':'authorized','reject':'rejected','cancel':'cancelled'}[action]
            if action=='authorize':change['order']={'order_id':task_id,'plan_digest':change['plan_digest'],'operation':'load_retained_import','authorized_by':actor}
            event(change,action,actor,payload.reason);save(task_id,record);return view(task_id)
        if action!='execute' or change['state']!='authorized' or not valid(record):raise HTTPException(409,'An authorized import CO is required')
        _,checksum=snapshot(task_id)
        if checksum!=change['plan_digest']:raise HTTPException(409,'Import baseline changed')
        change['state']='executing';event(change,'execute',actor,payload.reason);save(task_id,record)
        try:
            task=service()._restore_task(task_id)
            if not task:raise HTTPException(409,'Retained import could not be restored')
            task['load_change_digest']=checksum
            service()._persist_task(task_id)
            await service().commit_import(task_id)
        except Exception:
            change['state']='needs_recovery';event(change,'dispatch_unverified',actor);save(task_id,record);raise
        return view(task_id)
