"""Native product release requests; immutable packaging and outbox retain ownership."""
from copy import deepcopy
from pathlib import Path
import re
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from backend.depo_platform.change_requests import event,REVIEW_ACTIONS
from backend.depo_platform.bridge_contract import digest

PLAN_SCHEMA='nexus.native-product-release.v1'


def owner():
    from . import router
    return router


def request_key(version):return 'request:'+version


async def load(version):
    record=await owner()._product_io(owner().approval_store.get,request_key(version))
    if not record or record.get('kind')!='release_change' or record.get('request_id')!=version:
        raise HTTPException(404,'Product release request not found')
    return record


async def save(record):
    record['updated_at']=record['change_request']['history'][-1]['at']
    native=owner()
    from backend.mesh_store import PostgresRegistry
    if isinstance(native.approval_store,PostgresRegistry):
        from backend.oslc_service.notifications import retain_native_change
        return await native._product_io(retain_native_change,native.approval_store,request_key(record['request_id']),record,'product_changes',record['request_id'])
    return await native._product_io(native.approval_store.put,request_key(record['request_id']),record)


async def checked_payload(payload):
    native=owner();artifacts,errors=await native._product_io(native._validate,payload)
    if len(artifacts)>2000:raise HTTPException(422,'A release review supports at most 2000 retained artifacts')
    if errors:raise HTTPException(422,{'errors':errors})
    return artifacts,await native._product_io(native.publication_digest,payload,artifacts)


def valid_order(record):
    change=record.get('change_request');order=change.get('order') if isinstance(change,dict) else None
    plan=record.get('plan_digest')
    from backend.depo_platform.approval_matrix import order_valid as matrix_order_valid
    return (matrix_order_valid(change) and isinstance(order,dict) and isinstance(plan,str) and re.fullmatch('[0-9a-f]{64}',plan) is not None
        and change.get('request_id')==record.get('request_id') and change.get('plan_digest')==plan
        and change.get('state') in ('authorized','executing','awaiting_delivery','executed','needs_recovery')
        and order.get('order_id')==record.get('request_id') and order.get('plan_digest')==plan
        and order.get('operation')=='publish_product_version' and order.get('publish') is True
        and isinstance(order.get('authorized_by'),str) and bool(order['authorized_by'].strip()))


async def view(version):
    record=await load(version);native=owner();retained=await native._product_io(native.store.get,version)
    if retained and record['change_request']['state'] in {'executing','needs_recovery','awaiting_delivery','executed'}:
        current=retained.get('publication_digest')
    else:_,current=await checked_payload(record['publication'])
    change=deepcopy(record['change_request'])
    return {'preview_id':version,'product_version':version,'current_plan_digest':current,'plan_schema':PLAN_SCHEMA,
        'change_request':change,'scope_changed':current!=record['plan_digest'],'already_applied':False,
        'authorization_valid':valid_order(record) and current==record['plan_digest'],
        'scope':'Publish this exact product version and verify package integrity and catalog delivery',
        'product_name':record['name'],'artifact_count':len(record['publication']['artifacts']),
        'artifact_evidence':record.get('artifact_evidence',[]),
        'contract':{key:record['publication'].get(key) for key in ('product_id','version','owner','steward','classification','product_kind','semantic_releases')},
        'delivery_state':retained.get('status') if retained else 'Not packaged'}


async def submit(publication,reason,actor):
    if not isinstance(actor,str) or not actor.strip():raise HTTPException(403,'Verified product approval access is required')
    if not reason.strip():raise HTTPException(422,'Provide the business reason for release review')
    native=owner();payload={k:deepcopy(v) for k,v in publication.items() if k not in {'approved_by','approval_token','authorization','api_key'}}
    artifacts,plan=await checked_payload(payload);version=native._key(payload)
    # Check current release authority without treating proposal validation as approval.
    try:
        await native.resolve_lineage(payload,artifacts)
        for release in payload['semantic_releases']:await native.resolve_approved_release(release)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    except RuntimeError as exc:raise HTTPException(503,str(exc)) from None
    async with native._product_lock(version) as acquired:
        if not acquired:raise HTTPException(409,'Product operation is active; refresh before submitting')
        previous=await native._product_io(native.approval_store.get,request_key(version))
        if previous:
            if previous.get('plan_digest')!=plan:raise HTTPException(409,'This product version already has a different release request; use a new version')
            return await view(version)
        if await native._product_io(native.store.get,version):raise HTTPException(409,'An existing package cannot be retroactively approved')
        payload['idempotency_key']='governed-product-'+digest({'version':version,'plan':plan})
        change={'request_id':version,'revision':0,'state':'submitted','plan_digest':plan,'requested_by':actor,
            'reason':reason,'order':None,'history':[]}
        await run_in_threadpool(event,change,'submit',actor,reason)
        record={'kind':'release_change','request_id':version,'product_id':payload['product_id'],'version':payload['version'],
            'name':payload['name'],'artifact_evidence':[{'artifact_id':meta['artifact_id'],'filename':Path(str(meta.get('original_filename') or meta.get('filename') or path.name)).name} for meta,path in artifacts],
            'plan_digest':plan,'publication':payload,'change_request':change,'created_at':change['history'][0]['at']}
        await save(record);return await view(version)


async def verify_package(record):
    native=owner();retained=await native._product_io(native.store.get,record['request_id'])
    if (not retained or f"{retained.get('product_id')}:{retained.get('version')}"!=record['request_id'] or retained.get('publication_digest')!=record['plan_digest']
        or retained.get('idempotency_key')!=record['publication']['idempotency_key']
        or retained.get('approved_by')!=record['change_request']['order']['authorized_by']):
        raise HTTPException(409,'No exact matching native package receipt is retained; no publication was replayed')
    storage=retained.get('package_storage') or {}
    try:
        await native._product_io(native.verify_package,Path(storage.get('package_dir','')),Path(storage.get('zip_path','')),retained.get('manifest'))
    except ValueError:raise HTTPException(409,'Retained package integrity could not be verified; no publication was replayed') from None
    return retained


from backend.depo_platform.release_chain import guarded as release_guard

@release_guard(lambda payload,*args,**kwargs:('product_changes',owner()._key(payload),owner().store))
async def guarded_publish(payload,actor,artifacts,revision=None,expected_plan=None):
    native=owner();version=native._key(payload)
    record=await native._product_io(native.approval_store.get,request_key(version))
    if not record:return await native._publish_locked(payload,actor,artifacts)
    change=record['change_request'];plan=await native._product_io(native.publication_digest,payload,artifacts)
    if (plan!=record['plan_digest'] or revision is not None and revision!=change['revision']
        or expected_plan is not None and expected_plan!=plan or not valid_order(record)):
        raise HTTPException(409,'The exact product release scope must be authorized; refresh the request')
    if change['state'] in {'executed','awaiting_delivery'}:
        return native._public_product(await verify_package(record))
    if change['state']!='authorized':raise HTTPException(409,'Uncertain publication must be reconciled; do not replay the write')
    change['state']='executing';event(change,'execute',actor);await save(record)
    try:
        await native._publish_locked(record['publication'],change['order']['authorized_by'],artifacts)
        retained=await verify_package(record)
        change['state']='executed' if retained.get('status')=='published' and retained.get('catalog_registered_at') else 'awaiting_delivery'
        record['package_receipt']={key:retained.get(key) for key in ('publication_digest','catalog_registered_at','status')}
        record['package_receipt']['product_version']=version
        event(change,'package_receipt',actor);await save(record)
        return native._public_product(retained)
    except Exception:
        change['state']='needs_recovery';event(change,'execution_unverified',actor);await save(record)
        raise


async def command(version,action,actor,revision,expected_plan,reason=''):
    if not isinstance(actor,str) or not actor.strip():raise HTTPException(403,'Verified product approval access is required')
    native=owner()
    async with native._product_lock(version) as acquired:
        if not acquired:raise HTTPException(409,'Product operation is active; refresh before deciding')
        record=await load(version);change=record['change_request']
        if action in {'reconcile','retry_delivery'}:
            artifacts=[];current=record['plan_digest']
        else:artifacts,current=await checked_payload(record['publication'])
        if change['revision']!=revision or current!=expected_plan or current!=record['plan_digest']:
            raise HTTPException(409,'Release request or artifact scope changed; refresh before deciding')
        if action=='execute':
            await guarded_publish(record['publication'],actor,artifacts,revision,expected_plan)
            return await view(version)
        if action in {'reconcile','retry_delivery'}:
            if change['state'] not in {'executing','needs_recovery','awaiting_delivery'} or not valid_order(record):
                raise HTTPException(409,'No authorized package outcome is awaiting verification')
            retained=await verify_package(record)
            if action=='retry_delivery':
                if retained.get('status')!='pending_catalog_registration':raise HTTPException(409,'Only pending catalog delivery can be retried')
                updated=await native._register_catalog(retained)
                if not await native._product_io(native.store.compare_and_put,version,retained,updated):raise HTTPException(409,'Product delivery state changed; refresh')
                retained=updated
            change['state']='executed' if retained.get('status')=='published' and retained.get('catalog_registered_at') else 'awaiting_delivery'
            record['package_receipt']={key:retained.get(key) for key in ('publication_digest','catalog_registered_at','status')}
            record['package_receipt']['product_version']=version
        else:
            if action not in REVIEW_ACTIONS or change['state'] not in REVIEW_ACTIONS[action]:raise HTTPException(409,'This decision is not allowed in the current request state')
            if action=='reject' and not reason.strip():raise HTTPException(422,'Provide a reason for returning this release request')
            change['state']={'accept':'accepted','reject':'rejected','authorize':'authorized','cancel':'cancelled'}[action]
            if action=='authorize':change['order']={'order_id':version,'plan_digest':current,'operation':'publish_product_version','publish':True,'authorized_by':actor}
        event(change,action,actor,reason);await save(record);return await view(version)
