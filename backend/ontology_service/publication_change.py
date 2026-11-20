"""Reviewed ontology graph publication on the existing native queue record."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import re
import uuid
from fastapi import HTTPException
from backend.depo_platform.bridge_contract import digest
from backend.depo_platform.change_requests import event,REVIEW_ACTIONS
from backend.depo_platform.network import publication_job_timeout_seconds,bounded_timeout_seconds

PLAN_SCHEMA='nexus.native-ontology-publication.v1'


def owner():
    from . import router
    from .publication_jobs import publication_jobs
    return router,publication_jobs


def fingerprint(ontology_id):
    native,_=owner()
    try:
        metadata,content=native.catalog.read_artifact(ontology_id)
        checksum=hashlib.sha256(content).hexdigest()
        release=native.releases.verify_artifact(ontology_id,checksum)
    except LookupError:raise HTTPException(404,'Retained ontology was not found') from None
    except (ValueError,OSError):raise HTTPException(409,'Restore and validate the retained ontology release before review') from None
    plan={'ontology_id':ontology_id,'artifact_sha256':checksum,'prefix':metadata.get('prefix'),
        'lifecycle_status':metadata.get('lifecycle_status'),'status':metadata.get('status'),
        'release':{key:release.get(key) for key in ('family_id','version','predecessor_id','artifact_sha256')} if release else None}
    return metadata,plan,digest(plan)


def valid_order(job):
    change=job.get('change_request');order=change.get('order') if isinstance(change,dict) else None
    plan=change.get('plan') if isinstance(change,dict) else None
    checksum=change.get('plan_digest') if isinstance(change,dict) else None
    from backend.depo_platform.approval_matrix import order_valid as matrix_order_valid
    return (matrix_order_valid(change) and isinstance(order,dict) and isinstance(plan,dict) and isinstance(checksum,str)
        and re.fullmatch('[0-9a-f]{64}',checksum) is not None and digest(plan)==checksum
        and change.get('request_id')==job.get('ontology_id')==plan.get('ontology_id')
        and plan.get('artifact_sha256')==job.get('artifact_sha256')
        and change.get('state') in {'authorized','executing','needs_recovery','executed'}
        and order.get('order_id')==job.get('ontology_id') and order.get('plan_digest')==checksum
        and order.get('operation')=='publish_ontology_artifact' and order.get('publish') is True
        and isinstance(order.get('authorized_by'),str) and bool(order['authorized_by'].strip())
        and job.get('approved_by')==order['authorized_by'])


def current_receipt(value,job):
    if not isinstance(value,dict):return False
    receipt=value.get('receipt') or value
    return (isinstance(receipt,dict) and receipt.get('status')=='published' and receipt.get('current') is True
        and receipt.get('ontology_id')==job.get('ontology_id') and receipt.get('publication_id')==job.get('artifact_sha256')
        and all(type(receipt.get(key)) is int and receipt[key]>=0 for key in ('resources','relationships')))


def worker_state(job):
    """Project native queue outcomes into managed history; never infer a receipt."""
    if not job.get('change_request'):return job
    job=deepcopy(job);change=job['change_request'];old=change['state']
    if job.get('status')=='published':
        if valid_order(job) and current_receipt(job.get('result'),job):
            change['state']='executed'
            change['receipt']={'ontology_id':job['ontology_id'],'publication_id':job['artifact_sha256'],'current':True}
        else:
            job['status']='reconciliation_required';job['reconciliation_required']=True;change['state']='needs_recovery'
    elif job.get('status')=='timed_out' and not job.get('attempt') and valid_order(job):
        change['state']='authorized';job['reconciliation_required']=False
    elif job.get('status') in {'reconciliation_required','timed_out','failed'}:change['state']='needs_recovery'
    if change['state']!=old:event(change,'verify_graph_receipt' if change['state']=='executed' else 'queue_expired_without_dispatch' if change['state']=='authorized' else 'execution_unverified','ontology-publication-worker')
    return job


def view(ontology_id):
    metadata,plan,checksum=fingerprint(ontology_id);native,jobs=owner();job=jobs.get(ontology_id)
    change=job.get('change_request') if job else None
    return {'preview_id':ontology_id,'ontology_id':ontology_id,'ontology_name':metadata.get('name') or ontology_id,
        'current_plan_digest':checksum,'plan_schema':PLAN_SCHEMA,'artifact_sha256':plan['artifact_sha256'],
        'change_request':deepcopy(change),'scope_changed':bool(change and checksum!=change.get('plan_digest')),
        'authorization_valid':bool(job and valid_order(job) and change['plan_digest']==checksum),
        'scope':'Queue only this exact approved ontology artifact for graph publication; native worker verifies delivery',
        'already_applied':bool(job and not change and job.get('status')!='review_pending'),
        'release':plan['release'],'prefix':plan['prefix'],'lifecycle_status':plan['lifecycle_status']}


def transition(ontology_id,action,actor,revision,expected_plan,reason=''):
    if not isinstance(actor,str) or not actor.strip():raise HTTPException(403,'Verified ontology approval access is required')
    native,jobs=owner()
    with jobs.registry.advisory_lock(ontology_id) as acquired:
        if not acquired:raise HTTPException(409,'Publication worker or reviewer is active; refresh retained status')
        return native.catalog.with_publication_lock(ontology_id,lambda:_transition_locked(ontology_id,action,actor,revision,expected_plan,reason))


def _transition_locked(ontology_id,action,actor,revision,expected_plan,reason):
    native,jobs=owner()
    metadata,plan,checksum=fingerprint(ontology_id);job=jobs.get(ontology_id);change=job.get('change_request') if job else None
    if checksum!=expected_plan or (change['revision'] if change else 0)!=revision:
        raise HTTPException(409,'Request revision or ontology scope changed; refresh before deciding')
    if change and change['plan_digest']!=checksum:raise HTTPException(409,'Retained release scope changed; prepare a new ontology release')
    if action=='submit':
        if not reason.strip():raise HTTPException(422,'Provide the business reason for graph publication')
        if change:return view(ontology_id)
        if job or native.graph_publications.get(ontology_id):raise HTTPException(409,'An existing publication cannot be retroactively approved; reconcile its native receipt')
        if metadata.get('lifecycle_status')!='approved' or metadata.get('status')=='superseded':raise HTTPException(409,'Approve the ontology release before requesting graph publication')
        from .publication_worker import verify
        existing=verify(ontology_id)
        if not isinstance(existing,dict) or existing.get('status')!='not_published' or existing.get('publication_idle') is not True:
            raise HTTPException(409,'Graph absence and idle state must be verified before a new request; reconcile any existing publication')
        change={'request_id':ontology_id,'revision':0,'state':'submitted','requested_by':actor,'reason':reason,
            'plan':plan,'plan_digest':checksum,'order':None,'history':[]}
        event(change,'submit',actor,reason)
        job={'job_id':str(uuid.uuid4()),'ontology_id':ontology_id,'ontology_name':metadata.get('name') or ontology_id,
            'artifact_sha256':plan['artifact_sha256'],'status':'review_pending','created_at':jobs.clock().isoformat(),'change_request':change}
    elif not change:raise HTTPException(404,'No ontology publication review request is retained')
    elif action=='execute':
        if change['state']!='authorized' or not valid_order(job):raise HTTPException(409,'The exact ontology release must be authorized before queueing')
        from backend.depo_platform.release_chain import operation
        with operation('publications',ontology_id,jobs.registry):pass
        current=jobs.clock();total=publication_job_timeout_seconds();queue=bounded_timeout_seconds('ONTOLOGY_PUBLICATION_QUEUE_TIMEOUT_SECONDS',default=600,maximum=86400)
        job.update(status='queued',reconciliation_required=False,next_attempt_at=None,recovery_action='wait_and_verify',queued_at=current.isoformat(),deadline_at=(current+timedelta(seconds=total)).isoformat(),
            queue_deadline_at=(current+timedelta(seconds=min(queue,total))).isoformat())
        change['state']='executing';event(change,'queue_authorized_publication',actor)
    elif action=='reconcile':
        if change['state'] not in {'executing','needs_recovery'} or not valid_order(job):raise HTTPException(409,'No authorized publication outcome is awaiting verification')
        from .publication_worker import verify
        receipt=verify(ontology_id)
        if not current_receipt(receipt,job):raise HTTPException(409,'No exact current graph receipt is verified; no write was replayed')
        job.update(status='published',result=receipt,reconciliation_required=False)
        change['state']='executed';change['receipt']={'ontology_id':ontology_id,'publication_id':plan['artifact_sha256'],'current':True}
        event(change,'verify_graph_receipt',actor)
    else:
        if action not in REVIEW_ACTIONS or change['state'] not in REVIEW_ACTIONS[action]:raise HTTPException(409,'This decision is not allowed in the current request state')
        if action=='reject' and not reason.strip():raise HTTPException(422,'Provide a reason for returning this request')
        change['state']={'accept':'accepted','reject':'rejected','authorize':'authorized','cancel':'cancelled'}[action]
        if action=='authorize':
            if metadata.get('lifecycle_status')!='approved' or metadata.get('status')=='superseded':raise HTTPException(409,'Ontology release is no longer approved')
            job['approved_by']=actor;change['order']={'order_id':ontology_id,'plan_digest':checksum,'operation':'publish_ontology_artifact','publish':True,'authorized_by':actor}
        if action=='cancel':job['status']='cancelled'
        event(change,action,actor,reason)
    job['updated_at']=jobs.clock().isoformat();jobs.save_managed(ontology_id,job)
    return view(ontology_id)


def worker_guard(job):
    if not job.get('change_request'):return
    if not valid_order(job) or job['change_request']['state']!='executing':raise ValueError('Managed publication order is invalid')
    _,_,checksum=fingerprint(job['ontology_id'])
    if checksum!=job['change_request']['plan_digest']:raise ValueError('Managed ontology publication scope changed')
    from backend.mesh_store import PostgresRegistry
    if isinstance(owner()[1].registry,PostgresRegistry):
        from backend.depo_platform.release_chain import check,ReleaseDependencyPending
        try:check('publications',job['ontology_id'])
        except HTTPException as exc:raise ReleaseDependencyPending('Release dependency is not ready; graph dispatch was not attempted') from exc


def dispatch_guard(ontology_id,actor,expected_sha256):
    _,jobs=owner();job=jobs.get(ontology_id)
    if not job or not job.get('change_request'):return
    if expected_sha256 is None or job.get('status')!='running' or actor!=job.get('approved_by') or expected_sha256!=job.get('artifact_sha256'):
        raise HTTPException(409,'Use the retained Change Control authorization and native publication worker')
    try:worker_guard(job)
    except ValueError:raise HTTPException(409,'The approved ontology artifact or release changed; review a new release') from None
