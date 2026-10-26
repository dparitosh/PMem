import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.ontology_service.companion_evidence import retained_mapping_evidence, search_terms


def test_projection_is_parameterized_bounded_and_preserves_scope():
    calls=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):calls.append(args)
        def fetchall(self):return [('review',{'sources':[{'ontology_name':'AP242'},{'ontology_name':'QIF'}], 'candidates':198,'ambiguous':182,'selected':0,'shacl_conforms':True,'owl_rl_performed':True,'missing_source_ids':['ap242'],'matching_policy':'lexical-context-v1','truncated':True})]
    @contextmanager
    def connect():yield SimpleNamespace(cursor=Cursor)
    result=retained_mapping_evidence(SimpleNamespace(_connect=connect),'What AP242 to QIF mappings are available?',ontology_id='selected',ontology_prefix='prefix')
    sql,args=calls[0]
    assert args==['%ap242%','%qif%','selected','prefix']
    assert 'LIMIT 6' in sql and 'SELECT p.key, jsonb_build_object' in sql
    assert 'turtle' not in sql and 'SELECT p.value ' not in sql
    text=result['evidence'][0]['description']
    assert 'Proposals: 198' in text and 'selected consolidations: 0' in text
    assert 'Source registrations are currently missing' in text
    assert 'publication is not verified' in text
    assert search_terms('AP242 QIF')==['ap242','qif']


def test_context_forwards_read_bearer_without_graph_gateway_key(monkeypatch):
    from backend.agentic_service import companion_context as module
    seen=[];real=httpx.AsyncClient
    def handle(request):
        seen.append(request)
        return httpx.Response(200,json={'evidence':[],'coverage':'bounded'})
    monkeypatch.setenv('ONTOLOGY_SERVICE_URL','http://ontology/api/v1')
    monkeypatch.setattr(module,'gateway_subscription_headers',lambda endpoint:{'Ocp-Apim-Subscription-Key':'ontology-key'})
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handle),**kw))
    result=asyncio.run(module.mapping_context('AP242 QIF mappings',headers={'Authorization':'Bearer read','Ocp-Apim-Subscription-Key':'graph-key'},ontology_id='qif'))
    assert result['status']=='available'
    assert seen[0].headers['authorization']=='Bearer read'
    assert seen[0].headers['ocp-apim-subscription-key']=='ontology-key'
    assert seen[0].url.params['ontology_id']=='qif'
    asyncio.run(module.mapping_context('product',headers={}))
    assert len(seen)==1


@pytest.mark.parametrize('graph_failure',[False,True])
def test_saved_review_answers_without_published_graph_and_retains_429(monkeypatch,graph_failure):
    from backend.agentic_service import companion as module
    from backend.agentic_service import companion_context,local_llm
    saved={'evidence_type':'mapping_review','resource_id':'review-id','label':'AP242 to QIF','description':'198 proposals; 182 ambiguous; zero selected. Publication not verified.','source':'ontology-service:retained-merge-review'}
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'evidence':[saved],'status':'available'}))
    request=httpx.Request('POST','https://provider.example/chat')
    failure=httpx.HTTPStatusError('limited',request=request,response=httpx.Response(429,request=request))
    monkeypatch.setattr(local_llm,'summarize',AsyncMock(side_effect=failure))
    monkeypatch.setenv('COMPANION_LLM_ENABLED','true');monkeypatch.setenv('USE_LLM','openai')
    real=httpx.AsyncClient
    def handle(request):
        if graph_failure:raise httpx.ConnectError('offline',request=request)
        return httpx.Response(200,json={'nodes':[],'relationships':[]})
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handle),**kw))
    result=asyncio.run(module.KnowledgeCompanion().ask('AP242 QIF mappings',headers={}))
    assert result['answerable'] is True
    assert '198 proposals' in result['response']
    assert result['generation']['provider']=='openai'
    assert result['generation']['status']=='rate_limited'
    assert 'HTTP 429' in result['generation']['action']
    assert result['retrieval']['graph_status']==('unavailable' if graph_failure else 'available')


def test_no_evidence_provides_recovery_instead_of_claiming_answer(monkeypatch):
    from backend.agentic_service import companion as module
    real=httpx.AsyncClient
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'nodes':[],'relationships':[]})),**kw))
    result=asyncio.run(module.KnowledgeCompanion().ask('unfindable product',headers={}))
    assert result['answerable'] is False
    assert 'verify its graph publication' in result['response']


def test_mapping_history_route_requires_read_access_before_loading_records(monkeypatch):
    import ast
    from pathlib import Path
    from fastapi import APIRouter,FastAPI,Depends,Query
    from fastapi.testclient import TestClient
    from backend.depo_platform import authorization,credentials
    from backend.ontology_service import companion_evidence
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('GRAPH_READ_TOKEN','read-fixture')
    monkeypatch.setattr(credentials,'uses_postgres',lambda:False)
    monkeypatch.setattr(authorization,'require_active_token',lambda *args:None)
    monkeypatch.setattr(authorization,'token_actor',lambda *args:'reader')
    calls=[]
    monkeypatch.setattr(companion_evidence,'retained_mapping_evidence',lambda *args,**kwargs:calls.append(kwargs) or {'evidence':[]})
    route=APIRouter()
    scope=dict(__name__='backend.ontology_service.router',__package__='backend.ontology_service',router=route,Depends=Depends,Query=Query,graph_read_identity=authorization.graph_read_identity,PostgresRegistry=lambda name:object())
    node=next(n for n in ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8')).body if getattr(n,'name','')=='companion_mapping_evidence')
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<companion-route>','exec'),scope)
    app=FastAPI();app.include_router(route)
    client=TestClient(app)
    assert client.get('/companion/mapping-evidence',params={'query':'AP242 QIF'}).status_code==403
    assert calls==[]
    response=client.get('/companion/mapping-evidence',params={'query':'AP242 QIF','ontology_id':'active'},headers={'Authorization':'Bearer read-fixture'})
    assert response.status_code==200
    assert calls==[{'ontology_id':'active','ontology_prefix':''}]
    assert client.get('/companion/mapping-evidence',params={'query':'x'*4001},headers={'Authorization':'Bearer read-fixture'}).status_code==422
    assert len(calls)==1
