"""CR/CO over the native publication job; immutable candidate preview is untouched."""
from copy import deepcopy
import re
from backend.depo_platform.bridge_contract import BridgeConflict,digest
from backend.depo_platform.change_requests import event,REVIEW_ACTIONS

PLAN_SCHEMA='nexus.native-mapping-plan.v1'


def preview(jobs,identifier):
    value=jobs.get(identifier)
    if (value.get('kind')!='preview' or value.get('job_id')!=identifier
        or not identifier.startswith('bridge-preview-')
        or value.get('publication_job_id')!=identifier.replace('bridge-preview-','bridge-publication-',1)
        or digest({k:v for k,v in value.items() if k!='preview_digest'})!=value.get('preview_digest')):
        raise BridgeConflict('Preview integrity changed; create a new mapping preview')
    return value


def selection(value,identifiers):
    if (not isinstance(identifiers,list) or not 1<=len(identifiers)<=2000
        or any(not isinstance(key,str) or not key for key in identifiers) or len(set(identifiers))!=len(identifiers)):
        raise ValueError('Choose distinct retained mapping candidates')
    by_id={row['candidate_id']:row for row in value['candidates']}
    if any(key not in by_id or by_id[key].get('eligible') is not True for key in identifiers):
        raise ValueError('Selection contains unknown or ineligible mapping candidates')
    return sorted(identifiers)


def plan(value,identifiers):
    return digest({'schema':PLAN_SCHEMA,'preview_id':value['job_id'],
        'preview_digest':value['preview_digest'],'candidate_ids':sorted(identifiers)})


def valid_order(change,identifier,publication_id,current_plan):
    order=change.get('order') if isinstance(change,dict) else None
    from backend.depo_platform.approval_matrix import order_valid as matrix_order_valid
    return (matrix_order_valid(change) and isinstance(identifier,str) and identifier.startswith('bridge-preview-')
        and publication_id==identifier.replace('bridge-preview-','bridge-publication-',1)
        and isinstance(order,dict) and change.get('request_id')==publication_id
        and change.get('state') in ('authorized','executing','executed','needs_recovery')
        and isinstance(current_plan,str) and re.fullmatch('[0-9a-f]{64}',current_plan) is not None
        and change.get('plan_digest')==current_plan and order.get('plan_digest')==current_plan
        and order.get('order_id')==publication_id and order.get('request_id')==publication_id
        and order.get('operation')=='publish_selected_mappings' and order.get('publish') is True
        and isinstance(order.get('authorized_by'),str) and bool(order['authorized_by'].strip()))


def save(jobs,job):
    history=job['change_request']['history']
    job['updated_at']=history[-1]['at']
    from backend.mesh_store import PostgresRegistry
    if isinstance(jobs.store,PostgresRegistry):
        from backend.oslc_service.notifications import retain_native_change
        return retain_native_change(jobs.store,job['job_id'],job,'bridges',job['job_id'])
    jobs.store.put(job['job_id'],job)


def view(jobs,identifier):
    value=preview(jobs,identifier);job=jobs.store.get(value['publication_job_id']) or {}
    change=deepcopy(job.get('change_request'))
    current=plan(value,change['candidate_ids']) if change else value['preview_digest']
    return {'preview_id':identifier,'plan_schema':PLAN_SCHEMA,'current_plan_digest':current,
        'change_request':change,'scope_changed':bool(change and change['plan_digest']!=current),
        'authorization_valid':bool(change and valid_order(change,identifier,value['publication_job_id'],current)
            and retained_plan(job)==current and job.get('approved_ids')==change['candidate_ids']
            and job.get('approved_by')==change['order']['authorized_by']),
        'already_applied':bool(job and not change),'scope':'Publish only the reviewed candidate links; does not merge ontologies or publish a data product',
        'publication_id':value['publication_job_id'],'ontology_id':value['ontology_id'],'import_task_id':value['import_task_id'],
        'candidates':[{'candidate_id':row['candidate_id'],'source_term':str(row.get('source_term') or row['candidate_id'])[:300],
            'ontology_term':str(row.get('ontology_term') or '')[:300],'eligible':row.get('eligible') is True,
            'mapping_type':str(row.get('mapping_type') or 'Not recorded')[:100],
            'mapping':str(row.get('mapping') or 'Not recorded')[:100],
            'confidence':row.get('confidence') if type(row.get('confidence')) in (int,float) and 0<=row['confidence']<=1 else None}
            for row in value['candidates']]}


def transition(jobs,identifier,action,actor,revision,expected_plan,reason='',candidate_ids=None):
    if not isinstance(actor,str) or not actor.strip():raise ValueError('Verified approval access is required')
    if action!='submit' and candidate_ids:raise ValueError('Candidate scope cannot be changed during review')
    if action=='execute':
        value=preview(jobs,identifier);job=jobs.get(value['publication_job_id']);change=job.get('change_request')
        if not change:raise BridgeConflict('Submit and authorize a mapping change request first')
        jobs.publish(identifier,change['candidate_ids'],actor,expected_change_revision=revision,expected_change_plan=expected_plan)
        return view(jobs,identifier)
    value=preview(jobs,identifier);publication_id=value['publication_job_id']
    with jobs.store.advisory_lock(publication_id) as acquired:
        if acquired is False:raise BridgeConflict('This mapping change is active; refresh before deciding')
        value=preview(jobs,identifier);job=jobs.store.get(publication_id);change=(job or {}).get('change_request')
        current=plan(value,change['candidate_ids']) if change else value['preview_digest']
        if change and change['plan_digest']!=current:raise BridgeConflict('Retained mapping plan changed; prepare a new review')
        permitted={current,value['preview_digest']} if action=='submit' and change else {current}
        if expected_plan not in permitted:raise BridgeConflict('Mapping plan changed; refresh the exact preview')
        if action=='submit':
            snapshot=value.get('snapshot') or {}
            if any(not isinstance(snapshot.get(key),str) or not re.fullmatch('[0-9a-f]{64}',snapshot[key]) for key in ('source','ontology')):
                raise BridgeConflict('A complete retained source and ontology baseline is required; create a new preview')
            chosen=selection(value,candidate_ids or [])
            if change:
                if chosen!=change['candidate_ids']:raise BridgeConflict('Existing request has a different selection; prepare a new preview')
                return view(jobs,identifier)
            if job:raise BridgeConflict('Existing native publications cannot be retroactively approved')
            if revision!=0 or not reason.strip():raise ValueError('Provide a business reason for the unsubmitted preview')
            change={'request_id':publication_id,'state':'submitted','revision':0,'plan_digest':plan(value,chosen),
                'candidate_ids':chosen,'snapshot_digest':digest(value['snapshot']),'requested_by':actor,'reason':reason,'history':[],'order':None}
            job={'job_id':publication_id,'kind':'publication','preview_id':identifier,'status':'change_submitted',
                'approved_ids':[],'created_at':None,'attempts':0,'ontology_id':value['ontology_id'],
                'import_task_id':value['import_task_id'],'preview_digest':value['preview_digest'],
                'snapshot':deepcopy(value['snapshot']),'change_request':change}
        else:
            if (not change or change['revision']!=revision or change['plan_digest']!=current
                or action not in REVIEW_ACTIONS or change['state'] not in REVIEW_ACTIONS[action]):
                raise BridgeConflict('Request changed or action is not allowed; refresh before deciding')
            if action=='reject' and not reason.strip():raise ValueError('Provide a reason for returning this request')
            if action=='reconcile':
                job=verified_result(jobs,value,job,current)  # Never calls publish.
                change=job['change_request'];change['state']='executed'
            else:
                change['state']={'accept':'accepted','reject':'rejected','authorize':'authorized','cancel':'cancelled'}[action]
                if action=='authorize':
                    change['order']={'order_id':publication_id,'request_id':publication_id,'plan_digest':current,
                        'authorized_by':actor,'operation':'publish_selected_mappings','publish':True}
                    job.update(approved_ids=change['candidate_ids'],approved_by=actor,status='approved')
                else:job['status']='change_'+change['state']
        event(change,action,actor,reason);job['change_request']=change
        if not job.get('created_at'):job['created_at']=change['history'][0]['at']
        save(jobs,job)
        return view(jobs,identifier)


from backend.depo_platform.release_chain import guarded as release_guard

@release_guard(lambda jobs,identifier,*args,**kwargs:('bridges',identifier.replace('bridge-preview-','bridge-publication-',1),jobs.store))
def guarded_publish(jobs,identifier,identifiers,actor,approval_policy=None,revision=None,expected_plan=None):
    """Called only under the existing native publication lock and semantic hold lock."""
    value=preview(jobs,identifier);job=jobs.store.get(value['publication_job_id']);change=(job or {}).get('change_request')
    if not change:raise BridgeConflict('Submit and authorize a Change Control request before mapping publication')
    current=plan(value,change['candidate_ids'])
    if (change['plan_digest']!=current or sorted(identifiers)!=change['candidate_ids']
        or revision is not None and revision!=change['revision'] or expected_plan is not None and expected_plan!=current):
        raise BridgeConflict('Authorized mapping scope or revision changed; refresh before executing')
    if not valid_order(change,identifier,value['publication_job_id'],current):
        raise BridgeConflict('An exact-scope native mapping order is required')
    if change['state']=='executed':return verified_result(jobs,value,job,current)
    if change['state']!='authorized':raise BridgeConflict('Uncertain publication must be reconciled; do not replay the write')
    change['state']='executing';event(change,'execute',actor);save(jobs,job)
    try:
        result=jobs._publish_locked(identifier,identifiers,change['order']['authorized_by'],approval_policy)
        job=jobs.get(job['job_id']);change=job['change_request'];change['state']='executed'
        event(change,'execution_receipt',actor);save(jobs,job)
        return job
    except Exception:
        job=jobs.get(job['job_id']);change=job['change_request'];change['state']='needs_recovery'
        event(change,'execution_unverified',actor);save(jobs,job)
        raise


def retained_plan(job):
    """Lightweight plan from retained scope; not a live source freshness check."""
    change=job.get('change_request');ids=change.get('candidate_ids') if isinstance(change,dict) else None
    baseline=job.get('snapshot') or {}
    if (not isinstance(ids,list) or not 1<=len(ids)<=2000
        or any(not isinstance(key,str) or not key for key in ids) or len(set(ids))!=len(ids)
        or not isinstance(job.get('preview_digest'),str) or not re.fullmatch('[0-9a-f]{64}',job['preview_digest'])
        or not isinstance(baseline,dict) or change.get('snapshot_digest')!=digest(baseline)
        or any(not isinstance(baseline.get(key),str) or not re.fullmatch('[0-9a-f]{64}',baseline[key]) for key in ('source','ontology'))):
        return None
    return plan({'job_id':job.get('preview_id'),'preview_digest':job['preview_digest']},ids)


def verified_result(jobs,value,job,current_plan):
    change=job['change_request']
    if (not valid_order(change,value['job_id'],job['job_id'],current_plan)
        or job.get('approved_ids')!=change['candidate_ids']
        or job.get('approved_by')!=change['order']['authorized_by']
        or retained_plan(job)!=current_plan):
        raise BridgeConflict('Retained publication scope does not match its change order; no write was replayed')
    return jobs._completed(job,jobs.graph.receipt(job['job_id']))
