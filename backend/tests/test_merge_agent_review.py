"""Agent review handoff cannot become a lifecycle approval command."""
import ast
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool
from backend.depo_platform.request_bodies import MergeChangeCommand, MergeChangeSubmission
from backend.agentic_service.transport_auth import downstream_inputs, tool_retry_allowed
from backend.agentic_service.workflow_receipts import verify_merge_request_receipt, lookup
from backend.agentic_service.input_contracts import validate_operation

ROOT=Path(__file__).resolve().parents[1]
TOOL={'id':'ontology.merge.change.submit','method':'POST','service':'ontology','path':'/ontologies/merges/{preview_id}/change/submit','mutates':True}
def inputs(**extras):return dict(preview_id='p',expected_revision=0,expected_plan_digest='a'*64,reason='Review the retained source alignment',**extras)
def receipt():
    return {'preview_id':'p','scope_changed':False,'current_plan_digest':'a'*64,'change_request':{'request_id':'p','plan_digest':'a'*64,'reason':inputs()['reason'],'state':'submitted'}}

@pytest.fixture
def native():
    tree=ast.parse((ROOT/'ontology_service/router.py').read_text(encoding='utf-8'))
    nodes=[n for n in tree.body if getattr(n,'name',None) in {'_merge_change_actor','merge_change_command','submit_merge_change'}]
    service=SimpleNamespace(change_transition=Mock(return_value=receipt()))
    auth=Mock(return_value='verified-owner')
    scope=dict(router=APIRouter(),Request=Request,Depends=Depends,HTTPException=HTTPException,MergeChangeCommand=MergeChangeCommand,
               MergeChangeSubmission=MergeChangeSubmission,approval_identity=auth,merges=service,run_in_threadpool=run_in_threadpool,__package__='backend.ontology_service')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(ROOT/'ontology_service/router.py'),'exec'),scope)
    app=FastAPI();app.include_router(scope['router'],prefix='/api/v1/ontologies')
    return TestClient(app),auth,service

def test_native_agent_endpoint_can_only_submit(native):
    client,auth,service=native
    body={k:v for k,v in inputs().items() if k!='preview_id'}
    response=client.post('/api/v1/ontologies/merges/p/change/submit',json=body)
    assert response.status_code==200
    service.change_transition.assert_called_once_with('p','submit','verified-owner',0,'a'*64,inputs()['reason'])
    assert response.json()['change_request']['state']=='submitted'

@pytest.mark.parametrize('extra',[{'action':'authorize'},{'publish':True},{'approved_by':'forged'},{'approval_token':'forged'},{'expected_revision':1}])
def test_native_submission_rejects_extra_authority(native,extra):
    client,auth,service=native;body={k:v for k,v in inputs().items() if k!='preview_id'};body.update(extra)
    assert client.post('/api/v1/ontologies/merges/p/change/submit',json=body).status_code==422
    service.change_transition.assert_not_called()

def test_rejected_native_actor_cannot_submit(native):
    client,auth,service=native;auth.side_effect=HTTPException(403,'Rejected')
    body={k:v for k,v in inputs().items() if k!='preview_id'}
    assert client.post('/api/v1/ontologies/merges/p/change/submit',json=body).status_code==403
    service.change_transition.assert_not_called()

def test_agent_transport_needs_approval_and_never_injects_body_authority():
    with pytest.raises(HTTPException):downstream_inputs(TOOL,inputs(),None)
    value=downstream_inputs(TOOL,inputs(approved_by='forged',approval_token='secret'),'verified')
    assert value=={k:v for k,v in inputs().items() if k!='preview_id'}
    with pytest.raises(ValueError):downstream_inputs(TOOL,inputs(action='authorize'),'verified')
    assert not tool_retry_allowed(TOOL,attempt=1,retries=3,status_code=503)

def test_catalog_and_live_input_contract_match(native):
    catalog=json.loads((ROOT/'agentic_service/catalog.json').read_text(encoding='utf-8'))
    governor=next(a for a in catalog['agents'] if a['id']=='ontology-governor')
    assert TOOL['id'] in governor['tools'] and 'ontology.merge.change.status' in governor['tools']
    selected=next(t for t in catalog['tools'] if t['id']==TOOL['id'])
    assert all(selected[k]==v for k,v in TOOL.items())
    validate_operation(native[0].app.openapi(),TOOL,inputs())
    with pytest.raises(ValueError):validate_operation(native[0].app.openapi(),TOOL,inputs(action='accept'))

@pytest.mark.parametrize('field,value',[('preview_id','foreign'),('scope_changed',True),('current_plan_digest','b'*64)])
def test_recovery_rejects_foreign_or_stale_evidence(field,value):
    value_receipt=receipt();value_receipt[field]=value
    with pytest.raises(ValueError):verify_merge_request_receipt(inputs(),value_receipt)

def test_recovery_does_not_claim_another_reason_or_plan():
    for key,value in [('reason','Another request'),('plan_digest','b'*64),('state','invented')]:
        evidence=receipt();evidence['change_request'][key]=value
        with pytest.raises(ValueError):verify_merge_request_receipt(inputs(),evidence)

def test_uncertain_submission_recovery_uses_get_only(monkeypatch):
    calls=[]
    async def request(client,method,url,**kwargs):
        calls.append((method,url));return httpx.Response(200,json=receipt())
    routes=SimpleNamespace(_base=lambda service:'https://native.test/api/v1',_bounded_tool_request=request)
    monkeypatch.setitem(sys.modules,'backend.agentic_service.router',routes)
    monkeypatch.setattr('backend.agentic_service.transport_auth.downstream_headers',lambda *args,**kwargs:{})
    result=asyncio.run(lookup({'pending_step':{'tool_id':TOOL['id'],'inputs':inputs()}},SimpleNamespace()))
    assert result['change_request']['state']=='submitted'
    assert calls==[('GET','https://native.test/api/v1/ontologies/merges/p/change')]
