"""Native merge CR/CO state. One retained preview, one lock, no second executor."""
from copy import deepcopy
from backend.depo_platform.change_requests import event, REVIEW_ACTIONS
from .merge_plan import merge_plan_digest, PLAN_SCHEMA, valid_merge_order


class ChangeConflict(ValueError):
    pass


def load(service, identifier):
    record = service.registry.get(identifier) if service.registry is not None else service._load().get(identifier)
    if not record or record.get('preview_id') not in {None,identifier}:
        raise ValueError('Merge preview not found')
    return record


def save(service, identifier, record):
    history=(record.get('change_request') or {}).get('history') or []
    if history and isinstance(history[-1],dict) and isinstance(history[-1].get('at'),str):
        record['updated_at']=history[-1]['at']
    from backend.mesh_store import PostgresRegistry
    if isinstance(service.registry,PostgresRegistry) and record.get('change_request'):
        from backend.oslc_service.notifications import retain_merge_change
        retain_merge_change(service.registry,identifier,record)
        return
    values = {identifier: record} if service.registry is not None else service._load()
    values[identifier] = record
    service._save(values, identifier)


def fingerprint(record):
    try:
        sources = record['sources']
        ids = [source['ontology_id'] for source in sources]
        import re
        if (not isinstance(sources,list) or not 2 <= len(sources) <= 16 or any(not isinstance(key,str) or not key.strip() or len(key)>300 for key in ids) or len(set(ids)) != len(ids) or ids != record['source_ontology_ids']
            or any(not re.fullmatch('[0-9a-f]{64}', source['artifact_sha256']) for source in sources)
            or not re.fullmatch('[0-9a-f]{64}', record['governance_policy_sha256'])):
            raise ValueError('Incomplete merge baseline')
        return merge_plan_digest(record)
    except (KeyError, TypeError, AttributeError):
        raise ValueError('This preview lacks an exact retained merge baseline; prepare a new preview') from None


def view(service, identifier):
    record = load(service, identifier)
    current = fingerprint(record)
    change = deepcopy(record.get('change_request'))
    return {'preview_id':identifier, 'plan_schema':PLAN_SCHEMA, 'current_plan_digest':current,
        'change_request':change, 'scope_changed':bool(change and change['plan_digest'] != current),
        'scope':'Create merged draft only; graph publication requires a separate native approval',
        'baseline':[{'ontology_id':s['ontology_id'],'artifact_sha256':s['artifact_sha256']} for s in record['sources']],
        'already_applied':bool(record.get('applied_result'))}


def transition(service, identifier, action, actor, expected_revision, expected_plan_digest, reason=''):
    if not isinstance(actor,str) or not actor.strip(): raise ValueError('A verified actor is required')
    with service._operation_lock(identifier) as acquired:
        if acquired is False: raise ChangeConflict('This merge is being reviewed or executed; refresh before retrying')
        record = load(service, identifier)
        plan = fingerprint(record)
        if expected_plan_digest != plan:
            raise ChangeConflict('The merge plan changed; prepare a new review')
        change = record.get('change_request')
        if action == 'submit' and change:
            if change['plan_digest'] != plan: raise ChangeConflict('The retained request belongs to a different merge plan')
            return view(service, identifier)  # Idempotent submit; never overwrites a decision.
        if action == 'submit':
            if record.get('background_validation'):
                from .merge_background import background_merges
                if not background_merges.is_complete(record): raise ChangeConflict('Wait for the retained merge validation to complete before submitting')
            if record.get('applied_result'): raise ChangeConflict('Historical applied merges cannot be retroactively approved')
            if expected_revision != 0: raise ChangeConflict('Refresh the proposal before submitting')
            if not reason.strip(): raise ValueError('Provide the business reason for this change')
            change = {'request_id':identifier, 'state':'submitted', 'revision':0, 'plan_digest':plan,
                'title':record.get('ontology_name') or 'Ontology merge', 'reason':reason,
                'requested_by':actor, 'history':[], 'order':None}
        else:
            if not change: raise ChangeConflict('Submit the change request before reviewing it')
            if change['plan_digest'] != plan or change['revision'] != expected_revision:
                raise ChangeConflict('The request or plan changed; refresh before deciding')
            allowed = REVIEW_ACTIONS
            if action not in allowed or change['state'] not in allowed[action]:
                raise ChangeConflict('This action is not allowed in the current request state')
            if action == 'reject' and not reason.strip(): raise ValueError('Provide a reason for returning this request')
            if action == 'reconcile':
                # Existing receipt verifies retained result and artifact content. No write is replayed.
                result = service.receipt(identifier)
                if result.get('preview_id') != identifier or result.get('status') != 'merged':
                    raise ChangeConflict('Native execution receipt could not be verified; no write was replayed')
                change['state']='executed'
                change['result_ontology_id']=result['ontology']['ontology_id']
            else:
                change['state']={'accept':'accepted','reject':'rejected','authorize':'authorized','cancel':'cancelled'}[action]
                if action == 'accept': change['accepted_by']=actor
                if action == 'authorize':
                    change['order']={'order_id':identifier, 'plan_digest':plan, 'authorized_by':actor,
                        'operation':'create_merged_draft', 'publish':False}
        event(change, action, actor, reason)
        record['change_request']=change
        save(service, identifier, record)
        return view(service, identifier)


def execute(service, identifier, actor, revision, plan):
    if not isinstance(actor,str) or not actor.strip(): raise ValueError('A verified actor is required')
    with service._operation_lock(identifier) as acquired:
        if acquired is False: raise ChangeConflict('This merge is being reviewed or executed; refresh before retrying')
        record=load(service, identifier);change=record.get('change_request')
        if not change or change['revision']!=revision or change['plan_digest']!=plan:
            raise ChangeConflict('The request or authorization changed; refresh before executing')
        return service._with_source_locks(identifier, lambda: service._apply(identifier, actor))


from backend.depo_platform.release_chain import guarded as release_guard

@release_guard(lambda service,identifier,*args,**kwargs:('merges',identifier,service.registry))
def guarded_apply(service, identifier, actor, approval_policy=None, publish_requested=False):
    if not isinstance(actor,str) or not actor.strip(): raise ValueError('A verified actor is required')
    record=load(service, identifier);change=record.get('change_request')
    if not change:
        return service._apply_native(identifier, actor, approval_policy=approval_policy)
    if publish_requested:
        raise ChangeConflict('This change order authorizes a merged draft only; request graph publication separately')
    if change['plan_digest'] != fingerprint(record):
        raise ChangeConflict('The authorized merge plan changed; prepare a new review')
    if change['state'] == 'executed':
        return service.receipt(identifier)
    if change['state'] != 'authorized' or not change.get('order'):
        raise ChangeConflict('An accepted request and exact-scope authorization are required; uncertain execution must be reconciled')
    if not valid_merge_order(change, identifier):
        raise ChangeConflict('The retained change order scope is invalid')
    change['state']='executing';event(change,'execute',actor)
    save(service, identifier, record)  # Durable intent before native writes.
    try:
        result=service._apply_native(identifier, change['order']['authorized_by'], approval_policy=approval_policy)
        record=load(service, identifier);change=record['change_request']
        change['state']='executed';change['result_ontology_id']=result['ontology']['ontology_id']
        event(change,'execution_receipt',actor)
        save(service, identifier, record)
        return result
    except Exception:
        # Preserve native evidence and uncertainty. Never automatically call apply again.
        record=load(service, identifier);change=record['change_request'];change['state']='needs_recovery'
        event(change,'execution_unverified',actor)
        save(service, identifier, record)
        raise
