from copy import deepcopy
import pytest
from fastapi import HTTPException
from backend.depo_platform import approval_matrix as matrix
from backend.depo_platform.change_requests import event

def policy(mode='ALL',separate=False):
 return {'name':'Engineering release','separate_requester':separate,'distinct_stage_actors':True,'expected_revision':0,'stages':[{'action':'accept','function':'Engineering','mode':mode,'members':['engineer-a','engineer-b']},{'action':'authorize','function':'Release','mode':'ALL','members':['release-owner']}]}

def request():
 c={'plan_digest':'a'*64,'state':'submitted','revision':0,'requested_by':'requester','history':[],'order':None};event(c,'submit','requester');return c

def decide(c,action,actor):
 c['state']='accepted' if action=='accept' else 'authorized'
 if action=='authorize':c['order']={'authorized_by':actor}
 event(c,action,actor)

def test_all_signoffs_are_bound_to_scope_and_gate_order():
 matrix.update(policy(),'admin');c=request();decide(c,'accept','engineer-a')
 assert c['state']=='submitted' and c['history'][-1]['stage_complete'] is False
 decide(c,'accept','engineer-a');assert len(c['approval_matrix']['signoffs'])==1
 decide(c,'accept','engineer-b');assert c['state']=='accepted'
 decide(c,'authorize','release-owner');assert matrix.order_valid(c)
 c['plan_digest']='b'*64;assert not matrix.order_valid(c)

def test_any_and_unassigned_actor():
 matrix.update(policy('ANY'),'admin');c=request()
 with pytest.raises(HTTPException) as failure:decide(deepcopy(c),'accept','outsider')
 assert failure.value.status_code==403
 decide(c,'accept','engineer-a');assert c['state']=='accepted'

def test_duties_and_requester_cannot_be_spoofed():
 p=policy(separate=True);p['stages'][0]['members']=['requester','engineer-a'];p['stages'][1]['members']=['engineer-a','release-owner'];matrix.update(p,'admin');c=request()
 with pytest.raises(HTTPException):decide(deepcopy(c),'accept','requester')
 p=policy('ANY');p['stages'][1]['members']=['engineer-a'];p['expected_revision']=1;matrix.update(p,'admin');c=request();decide(c,'accept','engineer-a')
 with pytest.raises(HTTPException):decide(c,'authorize','engineer-a')

def test_policy_edits_do_not_replace_frozen_matrix():
 matrix.update(policy(),'admin');c=request();p=policy('ANY');p['expected_revision']=1;matrix.update(p,'admin')
 assert c['approval_matrix']['policy']['revision']==1
 c['plan_digest']='b'*64;event(c,'rebase','requester');assert c['approval_matrix']['policy']['revision']==2 and not c['approval_matrix']['signoffs']

def test_admin_revision_and_invalid_configuration():
 with pytest.raises(ValueError):matrix.update({**policy(),'stages':[]},'admin')
 matrix.update(policy(),'admin')
 with pytest.raises(HTTPException) as failure:matrix.update(policy(),'admin')
 assert failure.value.status_code==409
 assert not matrix.order_valid(None)

def test_tampered_matrix_does_not_authorize():
 c=request();decide(c,'accept','owner');decide(c,'authorize','owner');assert matrix.order_valid(c)
 c['approval_matrix']['policy']['name']='tampered';assert not matrix.order_valid(c)


def test_approval_settings_have_typed_deployment_contract():
 from backend.ontology_service.app import app
 from backend.depo_platform.openapi_contract import contract_errors
 errors=contract_errors(app.openapi())
 assert not errors
 body=app.openapi()['paths']['/api/v1/admin/approval-matrix']['put']['requestBody']
 assert body['required'] is True
