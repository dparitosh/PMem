"""Compatibility chat aliases must retain canonical evidence/auth contracts."""
import ast
from pathlib import Path
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from backend.legacy.companion_routes import mount_companion_routes
from backend.agentic_service import router as canonical
from backend.depo_platform.authorization import graph_read_identity
from backend.depo_platform.openapi_contract import effective_routes


def application():
    app=FastAPI();mount_companion_routes(app,canonical.router);return app


def test_aliases_share_the_canonical_handlers_and_no_duplicate_engine():
    app=application()
    for path in ['/chat','/chat-stream','/chat/validate','/chat/jobs']:
        routes=[r for r in effective_routes(app.routes) if getattr(r,'path','') in {path,'/api/v1'+path}]
        assert len(routes)==2 and routes[0].endpoint is routes[1].endpoint
    source=Path('backend/main.py').read_text(encoding='utf-8')
    ast.parse(source)
    assert '_load_chat_generators' not in source and 'lazy Ollama fallback' not in source
    for path in ['backend/agent/chat.py','backend/agent/memory.py','backend/chains/vector.py','backend/chains/cypher.py']:
        assert not Path(path).exists()


def test_aliases_preserve_authorization_before_execution(monkeypatch):
    app=application();calls=[]
    def denied():raise HTTPException(403,'Not authorized')
    app.dependency_overrides[graph_read_identity]=denied
    async def execute(*args,**kwargs):calls.append(1);return {}
    monkeypatch.setattr(canonical,'_companion_chat',execute)
    with TestClient(app) as client:
        for path in ['/chat','/api/v1/chat','/chat/validate','/chat-stream','/chat/jobs']:
            assert client.post(path,json={'message':'Show engineering evidence'}).status_code==403
    assert calls==[]


def test_alias_uses_same_evidence_response_and_typed_scope(monkeypatch):
    app=application();app.dependency_overrides[graph_read_identity]=lambda:'reader';calls=[]
    async def execute(payload,request,**kwargs):
        calls.append(payload.message)
        return {'response':'Bearing requirement','evidence':[{'id':'requirement:1'}],'sources':['source:1'],'answerable':True,'session_id':'owned-session'}
    monkeypatch.setattr(canonical,'_companion_chat',execute)
    with TestClient(app) as client:
        for path in ['/chat','/api/v1/chat']:
            result=client.post(path,json={'message':'Show requirements','graph_context':{'ontology':'v1','node_id':'part:1'}})
            assert result.status_code==200 and result.json()['evidence']==[{'id':'requirement:1'}]
        assert client.post('/chat',json={'message':'Show evidence','graph_context':{'visibleGraph':{'nodes':[]}}}).status_code==422
    assert len(calls)==2


def test_alias_health_describes_actual_canonical_execution():
    with TestClient(application()) as client:
        root=client.get('/chat/health').json();modern=client.get('/api/v1/chat/health').json()
    assert root==modern and root['fail_closed'] is True and root['job_execution']=='synchronous'



def test_stream_alias_keeps_evidence_and_terminal_receipt(monkeypatch):
    import json
    app=application();app.dependency_overrides[graph_read_identity]=lambda:'reader'
    monkeypatch.setattr(canonical,'graph_read_identity',lambda request:'reader')
    monkeypatch.setattr(canonical.sessions,'open_session',lambda *args:{'session_id':'owned-session','expires_at':'2099-01-01T00:00:00Z'})
    async def execute(payload,request,on_token=None):
        await on_token('Bearing ')
        return {'response':'Bearing evidence','evidence':[{'id':'part:1'}],'sources':['source:1'],'answerable':True,'run_id':'run:1','retained_prompt_job_id':'turn:1'}
    monkeypatch.setattr(canonical,'_companion_chat',execute)
    with TestClient(app) as client:
        result=client.post('/chat-stream',json={'message':'Show bearing evidence'})
    assert result.status_code==200 and result.headers['x-session-id']=='owned-session'
    events=[json.loads(line[6:]) for line in result.text.splitlines() if line.startswith('data: ')]
    assert any(event.get('token')=='Bearing ' for event in events)
    assert any(event.get('evidence')==[{'id':'part:1'}] and event.get('retained_prompt_job_id')=='turn:1' for event in events)
    assert events[-1]=={'done':True}


import pytest

@pytest.mark.asyncio
async def test_legacy_completed_results_remain_owned_and_incomplete_jobs_do_not_replay(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from backend.depo_platform import authorization
    from fastapi import Request
    import pytest
    tree=ast.parse(Path('backend/main.py').read_text(encoding='utf-8'))
    node=next(n for n in tree.body if getattr(n,'name','')=='chat_job_status')
    node.decorator_list=[]
    rows={'old':{'session_id':'client-a','status':'completed','response':'Retained evidence'},'unfinished':{'session_id':'client-a','status':'running'}}
    monkeypatch.setattr(authorization,'graph_read_identity',lambda request:'reader')
    scope={'Request':Request,'HTTPException':HTTPException,'asyncio':asyncio,'_CHAT_JOBS':rows,'_CHAT_JOBS_LOCK':asyncio.Lock(),'_cleanup_chat_jobs':AsyncMock(),'get_shared_chat_job':lambda key:None}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<legacy-result>','exec'),scope)
    def request(owner):return Request({'type':'http','method':'GET','headers':[],'session_id_supplied':True,'session_id':owner})
    assert (await scope['chat_job_status'](request('client-a'),'old'))['response']=='Retained evidence'
    assert (await scope['chat_job_status'](request('client-a'),'unfinished'))['status']=='interrupted'
    assert rows['unfinished']['status']=='running'
    with pytest.raises(HTTPException) as error:await scope['chat_job_status'](request('client-b'),'old')
    assert error.value.status_code==403
