"""Versioned approval stages; native services retain locks and execution authority."""
from copy import deepcopy
from datetime import datetime, timezone
from fastapi import HTTPException
from backend.depo_platform.bridge_contract import digest
from backend.mesh_store import PostgresRegistry

configuration=PostgresRegistry('approval_matrix_v1')

STAGES=('accept','authorize')
DEFAULT={'revision':0,'name':'Credential-bound review','separate_requester':False,'distinct_stage_actors':False,
 'stages':[{'action':'accept','function':'Evidence reviewer','mode':'ANY','members':[]},
           {'action':'authorize','function':'Release authorizer','mode':'ANY','members':[]}]}

def current():
    return configuration.get('approval-matrix:current') or deepcopy(DEFAULT)

def validate(value):
    if not isinstance(value,dict) or set(value)-{'name','separate_requester','distinct_stage_actors','stages','expected_revision'}:
        raise ValueError('Unsupported approval matrix fields')
    if not isinstance(value.get('name'),str) or not 1<=len(value['name'].strip())<=120:
        raise ValueError('Provide a matrix name')
    if any(type(value.get(key)) is not bool for key in ('separate_requester','distinct_stage_actors')):
        raise ValueError('Separation settings must be boolean')
    rows=value.get('stages')
    if not isinstance(rows,list) or len(rows)!=2 or [r.get('action') if isinstance(r,dict) else None for r in rows]!=list(STAGES):
        raise ValueError('Configure evidence review followed by release authorization')
    for row in rows:
        if set(row)!={'action','function','mode','members'} or row['mode'] not in ('ALL','ANY'):
            raise ValueError('Use ALL or ANY signoff for each stage')
        if not isinstance(row['function'],str) or not 1<=len(row['function'].strip())<=120:
            raise ValueError('Provide the responsible job function')
        members=row['members']
        if not isinstance(members,list) or not 1<=len(members)<=30 or any(not isinstance(m,str) or not m.strip() or m!=m.strip() or len(m)>200 for m in members) or len(set(members))!=len(members):
            raise ValueError('Each stage needs 1–30 distinct authenticated principal names')
    if value['distinct_stage_actors'] and len(set(rows[0]['members']+rows[1]['members']))<2:
        raise ValueError('Separate review and authorization require different principals')
    return {key:deepcopy(value[key]) for key in ('name','separate_requester','distinct_stage_actors','stages')}

def update(value,actor):
    if not isinstance(actor,str) or not actor.strip():raise HTTPException(403,'Verified administrator required')
    clean=validate(value)
    with configuration.advisory_lock('approval-matrix') as acquired:
        if not acquired:raise HTTPException(409,'Approval settings are busy; refresh')
        previous=current()
        if type(value.get('expected_revision')) is not int or value['expected_revision']!=previous['revision']:
            raise HTTPException(409,'Approval matrix changed; refresh before saving')
        clean.update(revision=previous['revision']+1,updated_by=actor,updated_at=datetime.now(timezone.utc).isoformat())
        configuration.put_many({'approval-matrix:current':clean,'approval-matrix:version:'+str(clean['revision']):clean})
        return clean

def snapshot(change):
    matrix=deepcopy(current())
    change['approval_matrix']={'policy':matrix,'digest':digest(matrix),'plan_digest':(change.get('plan_digest') or change.get('configuration_id')),'signoffs':[]}

def verified(change):
    if not isinstance(change,dict):return False
    matrix=change.get('approval_matrix')
    if matrix is None:return True # Historical authority is not retroactively reassigned.
    return isinstance(matrix,dict) and isinstance(matrix.get('policy'),dict) and matrix.get('digest')==digest(matrix['policy']) and matrix.get('plan_digest')==(change.get('plan_digest') or change.get('configuration_id')) and isinstance(matrix.get('signoffs'),list)

def decide(change,action,actor):
    matrix=change.get('approval_matrix')
    if matrix is None:return True
    if not verified(change):raise HTTPException(409,'Approval matrix or reviewed scope changed; prepare a new request')
    policy=matrix['policy']; row=next(r for r in policy['stages'] if r['action']==action)
    if row['members'] and actor not in row['members']:raise HTTPException(403,'The authenticated principal is not assigned to this approval stage')
    if policy['separate_requester'] and actor==change.get('requested_by'):raise HTTPException(403,'The requester cannot approve this request')
    signs=matrix['signoffs']
    if policy['distinct_stage_actors'] and any(s['actor']==actor and s['action']!=action for s in signs):
        raise HTTPException(403,'Review and release authorization require different principals')
    if not any(s['actor']==actor and s['action']==action for s in signs):
        signs.append({'actor':actor,'action':action,'at':datetime.now(timezone.utc).isoformat(),'plan_digest':(change.get('plan_digest') or change.get('configuration_id'))})
    signed={s['actor'] for s in signs if s['action']==action and s.get('plan_digest')==(change.get('plan_digest') or change.get('configuration_id'))}
    complete=set(row['members']).issubset(signed) if row['mode']=='ALL' else bool(signed)
    if not complete:
        change['state']='submitted' if action=='accept' else 'accepted'
        if action=='authorize':change['order']=None
    elif action=='authorize' and isinstance(change.get('order'),dict):
        change['order']['approval_matrix_digest']=matrix['digest']
    return complete

def order_valid(change):
    if not verified(change):return False
    matrix=change.get('approval_matrix')
    if matrix is None:return True
    if (change.get('order') or {}).get('approval_matrix_digest')!=matrix['digest']:return False
    for row in matrix['policy']['stages']:
        signed={s['actor'] for s in matrix['signoffs'] if s.get('action')==row['action'] and s.get('plan_digest')==(change.get('plan_digest') or change.get('configuration_id')) and (not row['members'] or s.get('actor') in row['members'])}
        if not signed or row['mode']=='ALL' and not set(row['members']).issubset(signed):return False
    return True
