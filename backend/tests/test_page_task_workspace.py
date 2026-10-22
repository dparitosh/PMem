import uuid
from datetime import datetime,timezone
import pytest
from fastapi import FastAPI,Request
from fastapi.testclient import TestClient
from backend.mesh_store import InMemoryRegistry
from backend.agentic_service import page_tasks as tasks, sessions


@pytest.fixture
def workspace(monkeypatch):
    sources={kind:InMemoryRegistry() for kind in ('goal','workflow','tool')}
    monkeypatch.setattr(tasks,'stores',lambda:sources)
    monkeypatch.setattr(tasks,'graph_read_identity',lambda request:'reader')
    app=FastAPI();app.include_router(tasks.router)
    return TestClient(app),sources


def owner(token):
    request=Request({'type':'http','headers':[(b'authorization',('Bearer '+token).encode())]})
    return sessions.owner(request,'reader')


def record(token,page,identifier):
    principal=owner(token)
    return {'run_id':identifier,'owner':principal,**tasks.page_binding(principal,{'page':page,'ontology_id':'urn:source'}),
        'status':'completed','task_label':'Review evidence','created_at':datetime.now(timezone.utc).isoformat(),
        'execution_payload':{'private':'not public'},'credential_fingerprints':{'private':'never expose'}}


def test_history_is_scoped_to_current_identity_page_and_store(workspace):
    client,sources=workspace
    for kind in sources:
        for token,page in [('one','home'),('one','graph'),('two','home')]:
            row=record(token,page,kind+token+page);sources[kind].put(row['run_id'],row)
    response=client.get('/api/v1/page-tasks?page=home',headers={'Authorization':'Bearer one'})
    assert response.status_code==200
    rows=response.json()['tasks']
    assert len(rows)==3 and all('onehome' in row['run_id'] for row in rows)
    assert 'never expose' not in response.text and 'execution_payload' not in response.text
    assert client.get('/api/v1/page-tasks?page=unknown').status_code==422
    assert client.get('/api/v1/page-tasks?page=home&limit=500').status_code==422


def test_detail_rechecks_ownership_before_returning_any_task(workspace):
    client,sources=workspace
    row=record('one','graph','read-one');sources['tool'].put(row['run_id'],row)
    assert client.get('/api/v1/page-tasks/tool/read-one',headers={'Authorization':'Bearer two'}).status_code==403
    response=client.get('/api/v1/page-tasks/tool/read-one',headers={'Authorization':'Bearer one'})
    assert response.status_code==200 and response.json()['run_id']=='read-one'
    assert 'owner' not in response.json() and 'page_owner' not in response.json()
    assert 'execution_payload' not in response.text and 'credential_fingerprints' not in response.text


def test_history_outage_is_recoverable_without_dispatching_any_task(workspace,monkeypatch):
    client,sources=workspace
    def unavailable(**kwargs): raise OSError('private DB data')
    monkeypatch.setattr(sources['goal'],'page',unavailable)
    response=client.get('/api/v1/page-tasks?page=home',headers={'Authorization':'Bearer one'})
    assert response.status_code==503 and 'private' not in response.text


def test_expired_tool_details_do_not_claim_the_process_is_still_running(workspace):
    client,sources=workspace
    row={**record('one','graph','expired'),'status':'running','deadline_at':'2000-01-01T00:00:00+00:00'}
    sources['tool'].put(row['run_id'],row)
    response=client.get('/api/v1/page-tasks/tool/expired',headers={'Authorization':'Bearer one'})
    assert response.json()['status']=='interrupted'
    assert sources['tool'].get('expired')['status']=='running'  # projection never claims a write cancellation


def test_page_metadata_cannot_change_authority_or_retain_arbitrary_headers():
    bound=tasks.page_binding('owner',{'page':'data-catalog','headers':{'Authorization':'secret'},'owner':'forged','ontology_id':'a'})
    assert bound['page_context']=={'page':'catalog','ontology_id':'a'}
    assert 'secret' not in str(bound) and 'forged' not in str(bound)


from backend.tests.test_read_goal_routes import setup


def test_goal_submission_recovers_original_task_and_rejects_changed_intent(setup):
    client,store,_=setup
    payload={'task':'Inspect selected source','context':{'page':'ontology','ontology_id':'selected'},'submission_id':str(uuid.uuid4())}
    headers={'Authorization':'Bearer owner-one'}
    first=client.post('/api/v1/agents/reviewer/goals',json=payload,headers=headers)
    second=client.post('/api/v1/agents/reviewer/goals',json=payload,headers=headers)
    assert first.status_code==202 and first.json()['run_id']==second.json()['run_id'] and len(store.records)==1
    changed=client.post('/api/v1/agents/reviewer/goals',json={**payload,'task':'Different task'},headers=headers)
    assert changed.status_code==409 and len(store.records)==1
    public=first.json()
    assert public['page_context']['page']=='ontology' and 'page_owner' not in public and 'submission_fingerprint' not in public
    original=next(iter(store.records.values()))
    assert original['page_owner']==tasks.page_binding(original['owner'],{'page':'ontology'})['page_owner']


def test_unknown_task_page_cannot_enqueue_an_execution(setup):
    client,store,_=setup
    response=client.post('/api/v1/agents/reviewer/goals',json={'task':'Inspect','context':{'page':'missing'}},headers={'Authorization':'Bearer owner-one'})
    assert response.status_code==422 and not store.records
