import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from backend.agentic_service import router, sessions, ontology_orchestrator
from backend.agentic_service.app import app
from backend.mesh_store import InMemoryRegistry


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('GRAPH_READ_TOKEN', 'reader')
    monkeypatch.setenv('GRAPH_SERVICE_URL', 'http://graph/api/v1')
    return TestClient(app)


READ = {'Authorization': 'Bearer reader'}


@pytest.mark.parametrize('value', ['..', '../merges', 'x?redirect=1', 'a#b', '%2f', 'x\\y', '\n'])
def test_tool_path_cannot_escape_operation(value):
    with pytest.raises(ValueError):
        router._render('/ontologies/{ontology_id}/transition', {'ontology_id': value})


def test_tool_path_encodes_resource_name():
    assert router._render('/a/{id}', {'id': 'urn:test value'}) == '/a/urn%3Atest%20value'


@pytest.mark.parametrize('reference', ['$steps.0.result.id', '$steps.-1.result.id', '$steps.2.result.id'])
def test_reference_only_reads_completed_prior_steps(reference):
    with pytest.raises(ValueError):
        router._lookup(reference, [{'status': 'completed', 'result': {'id': 'first'}}])


def test_whole_result_and_list_reference():
    traces = [{'result': {'items': [{'id': 'first'}]}}]
    assert router._lookup('$steps.1.result', traces) == traces[0]['result']
    assert router._lookup('$steps.1.result.items.0.id', traces) == 'first'


def workflow(monkeypatch):
    store = InMemoryRegistry('workflow-state-test')
    monkeypatch.setattr(router, 'workflow_store', store)
    monkeypatch.setattr(router.catalog, 'read', lambda: {
        'agents': [{'id': 'reader', 'tools': ['read']}],
        'tools': [{'id': 'read', 'mutates': False}],
        'workflows': [{'id': 'test', 'steps': [{'agent_id': 'reader', 'tool_id': 'read'}]}]})
    return store


def test_unresolvable_reference_finishes_state_and_telemetry(client, monkeypatch):
    store = workflow(monkeypatch)
    result = client.post('/api/v1/workflow-runs', headers=READ,
                         json={'workflow_id': 'test', 'inputs': {'id': '$steps.1.result.id'}})
    assert result.status_code == 422
    record = store.get(result.headers['X-DEPO-Run-ID'])
    assert record['status'] == 'failed' and record['finished_at']
    assert record['traces'][0]['attempt'] == 0
    assert router.telemetry.recent()[0]['status'] == 'failed'


@pytest.mark.parametrize('error', [RuntimeError('failure'), asyncio.CancelledError()])
@pytest.mark.asyncio
async def test_unexpected_failure_or_cancellation_finishes_workflow(monkeypatch, error):
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('GRAPH_READ_TOKEN', 'reader')
    store = workflow(monkeypatch)
    async def dispatch(*args):
        raise error
    monkeypatch.setattr(router, '_dispatch', dispatch)
    request = SimpleNamespace(headers=Headers(READ), state=SimpleNamespace())
    with pytest.raises((HTTPException, asyncio.CancelledError)):
        await router.run_workflow({'workflow_id': 'test'}, request)
    record = store.recent()[0]
    expected = 'interrupted' if isinstance(error, asyncio.CancelledError) else 'failed'
    assert record['status'] == expected
    assert router.telemetry.recent()[0]['status'] == expected


def test_deadline_finishes_workflow(client, monkeypatch):
    store = workflow(monkeypatch)
    monkeypatch.setenv('AGENTIC_RUN_TIMEOUT_SECONDS', '0.01')
    async def dispatch(*args):
        await asyncio.sleep(1)
    monkeypatch.setattr(router, '_dispatch', dispatch)
    result = client.post('/api/v1/workflow-runs', headers=READ, json={'workflow_id': 'test'})
    assert result.status_code == 504
    assert store.get(result.headers['X-DEPO-Run-ID'])['status'] == 'timed_out'
    assert router.telemetry.summary()['timed_out'] == 1


def test_dead_process_read_projects_interrupted_without_overwriting(client, monkeypatch):
    store = workflow(monkeypatch)
    store.put('dead', {'status': 'running', 'deadline_at': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()})
    result = client.get('/api/v1/workflow-runs/dead', headers=READ)
    assert result.json()['status'] == 'interrupted'
    assert result.json()['reconciliation_required']
    assert store.get('dead')['status'] == 'running'


def test_session_stable_owned_and_expires(client, monkeypatch):
    clock = datetime(2026, 10, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(sessions, 'now', lambda: clock)
    request = SimpleNamespace(headers=Headers(READ))
    record = sessions.open_session(request, 'reader')
    clock += timedelta(seconds=5)
    reused = sessions.open_session(request, 'reader', record['session_id'])
    assert reused['session_id'] == record['session_id']
    assert reused['expires_at'] == record['expires_at']
    with pytest.raises(HTTPException) as mismatch:
        sessions.open_session(SimpleNamespace(headers=Headers({'Authorization': 'Bearer other'})), 'reader', record['session_id'])
    assert mismatch.value.status_code == 403
    clock += timedelta(seconds=1801)
    resumed = sessions.open_session(request, 'reader', record['session_id'])
    assert resumed['session_id'] == record['session_id']
    assert resumed['status'] == 'active'
    assert resumed['expires_at'] == record['expires_at']


def test_session_absolute_expiry_with_recent_activity(client, monkeypatch):
    clock = datetime(2026, 10, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(sessions, 'now', lambda: clock)
    record = sessions.open_session(SimpleNamespace(headers=Headers(READ)), 'reader')
    clock += timedelta(days=1)
    record['last_seen_at'] = clock.isoformat()
    sessions.store.put(record['session_id'], record)
    with pytest.raises(HTTPException) as expired:
        sessions.open_session(SimpleNamespace(headers=Headers(READ)), 'reader', record['session_id'])
    assert expired.value.status_code == 410


def test_chat_response_and_telemetry_share_session(client, monkeypatch):
    async def ask(*args, **kwargs):
        return {'response': 'Evidence', 'evidence': [], 'sources': [], 'answerable': False}
    monkeypatch.setattr(router.companion, 'ask', ask)
    response = client.post('/api/v1/chat', headers=READ, json={'message': 'example'})
    assert response.status_code == 200
    session_id = response.json()['session_id']
    assert router.telemetry.recent()[0]['session_id'] == session_id
    assert response.json()['session_expires_at']


def test_chat_unexpected_error_finishes_telemetry(client, monkeypatch):
    async def ask(*args, **kwargs):
        raise TypeError('bad graph shape')
    monkeypatch.setattr(router.companion, 'ask', ask)
    response = client.post('/api/v1/chat', headers=READ, json={'message': 'example'})
    assert response.status_code == 503
    assert router.telemetry.recent()[0]['status'] == 'failed'


def test_jsonld_inline_context_supported_remote_context_rejected(tmp_path):
    path = tmp_path / 'sample.jsonld'
    path.write_text('{"@context":{"name":"https://example.test/name"},"@id":"https://example.test/item","name":"item"}')
    assert len(ontology_orchestrator._load(path)) == 1
    path.write_text('{"@context":"https://example.test/context"}')
    with pytest.raises(ValueError, match='remote contexts'):
        ontology_orchestrator._load(path)


def test_multipart_keeps_verified_approval():
    import base64
    form, _ = router._multipart({'file': {'filename': 'x.ttl', 'content_base64': base64.b64encode(b'x').decode()},
        'approved_by': 'verified', 'approval_token': 'server', 'form': {'approved_by': 'forged'}})
    assert form['approved_by'] == 'verified' and form['approval_token'] == 'server'


def test_telemetry_failure_does_not_change_completed_tool(client, monkeypatch):
    async def dispatch(*args):
        return {'tool_id': 'read', 'result': {'done': True}}
    monkeypatch.setattr(router, '_dispatch', dispatch)
    monkeypatch.setattr(router.telemetry, 'finish', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('database unavailable')))
    response = client.post('/api/v1/runs', headers=READ, json={'agent_id': 'graph-analyst', 'tool_id': 'graph.analytics'})
    assert response.status_code == 200 and response.json()['result']['done']


def test_companion_uses_credential_scoped_memory(client, monkeypatch):
    queries, recorded = [], []
    monkeypatch.setattr(router.AgentMemoryService, 'recent_context', lambda *args: {'messages': [{'role': 'user', 'text': 'Motor assembly'}]})
    monkeypatch.setattr(router.AgentMemoryService, 'record_chat_turn', lambda **kwargs: recorded.append(kwargs))
    async def ask(query, **kwargs):
        queries.append(query)
        return {'response': 'Evidence', 'evidence': [], 'sources': [], 'answerable': False}
    monkeypatch.setattr(router.companion, 'ask', ask)
    response = client.post('/api/v1/chat', headers=READ, json={'message': 'its components'})
    assert response.status_code == 200
    session = sessions.store.get(response.json()['session_id'])
    assert recorded[0]['session_id'] == sessions.memory_id(session)
    assert queries == ['Motor assembly its components']


def test_chat_job_honest_state_and_ownership(client, monkeypatch):
    monkeypatch.setattr(router, 'companion_job_store', InMemoryRegistry('jobs'))
    async def ask(*args, **kwargs):
        return {'response': 'Evidence', 'evidence': [], 'sources': [], 'answerable': False}
    monkeypatch.setattr(router.companion, 'ask', ask)
    response = client.post('/api/v1/chat/jobs', headers=READ, json={'message': 'product'})
    assert response.status_code == 200 and response.json()['status'] == 'completed'
    job_id = response.json()['job_id']
    assert client.get(f'/api/v1/chat/jobs/{job_id}', headers=READ).status_code == 200
    monkeypatch.setenv('GRAPH_READ_TOKEN', 'other')
    assert client.get(f'/api/v1/chat/jobs/{job_id}', headers={'Authorization': 'Bearer other'}).status_code == 403
