from contextlib import contextmanager
import copy
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.agentic_service import goal_routes as routes, goal_runner as engine
from backend.agentic_service.durable_workflows import credential_snapshot


class Store:
    def __init__(self): self.records = {}
    def create(self, key, value): self.records[key] = copy.deepcopy(value)
    put = create
    def get(self, key): return copy.deepcopy(self.records.get(key))
    @contextmanager
    def advisory_lock(self, key): yield True
    def page(self, *, limit, field, value):
        values = [v for v in self.records.values() if v.get(field) == value]
        return len(values), values[:limit]
    def compare_and_put(self, key, expected, value):
        if self.get(key) != expected: return False
        self.put(key, value)
        return True
    def find_by_field(self, field, value, limit=100, after_key=''):
        return [self.get(key) for key in sorted(self.records) if key > after_key and self.records[key].get(field) == value][:limit]


@pytest.fixture
def setup(monkeypatch):
    from backend.agentic_service import router as control
    from backend.agentic_service import execution_grants, local_llm
    monkeypatch.setattr(local_llm, 'settings', lambda: ('ollama', 'fixture-model', 'http://localhost', 10, {}))
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('AGENTIC_EXECUTION_MODE', 'worker')
    monkeypatch.setenv('GRAPH_READ_TOKEN', 'server-read-fixture')
    monkeypatch.setattr(routes, 'graph_read_identity', lambda request: 'reader')
    memory = Store()
    monkeypatch.setattr(routes, 'store', memory)
    monkeypatch.setattr(routes, 'heartbeats', Store())
    tool = {'id': 'graph.read', 'mutates': False, 'input_schema': {'type': 'object', 'properties': {
        'ontology_id': {'type': 'string'}}, 'required': ['ontology_id'], 'additionalProperties': False}}
    monkeypatch.setattr(routes, 'selected', lambda identifier: ({'id': identifier, 'tools': ['graph.read']}, [tool]))
    monkeypatch.setattr(execution_grants, 'execution_identity', lambda *args: (None, None, credential_snapshot({'GRAPH_READ_TOKEN'})))
    monkeypatch.setattr(execution_grants, 'verify_grant', lambda value: None)
    monkeypatch.setattr(control, '_proposal_tools', AsyncMock(side_effect=lambda tools, request: tools))
    monkeypatch.setattr(control, '_dispatch', AsyncMock(return_value={'result': {'iri': 'urn:Motor'}}))
    app = FastAPI(); app.include_router(routes.router)
    return TestClient(app), memory, control


def create(client, headers=None):
    return client.post('/api/v1/agents/reviewer/goals', json={'task': 'Find motor evidence',
        'context': {'ontology_id': 'selected'}}, headers=headers or {'Authorization': 'Bearer owner-one'})


def test_goal_is_durable_owned_and_does_not_persist_credentials(setup):
    client, store, _ = setup
    response = create(client)
    assert response.status_code == 202
    record = response.json()
    assert record['status'] == 'queued' and record['read_only'] is True
    assert 'owner' not in record and 'credential_fingerprints' not in record
    assert 'server-read-fixture' not in str(store.records) and 'owner-one' not in str(store.records)
    assert client.get('/api/v1/goals/' + record['run_id'], headers={'Authorization':'Bearer owner-two'}).status_code == 403


@pytest.mark.asyncio
async def test_worker_executes_retained_plan_and_binds_completed_evidence(setup, monkeypatch):
    client, store, control = setup
    identifier = create(client).json()['run_id']
    from backend.agentic_service import local_llm
    propose = AsyncMock(side_effect=[{'tool_id':'goal.plan','inputs':{'subtasks':['Inspect motor']}},
        {'tool_id':'graph.read','inputs':{'ontology_id':'selected'}},
        {'tool_id':'goal.complete','inputs':{'summary':'Motor evidence retained','evidence_steps':['observation-2']}}])
    monkeypatch.setattr(local_llm, 'suggest_tool', propose)
    await routes.execute_candidate(store.get(identifier))
    result = store.get(identifier)
    assert result['status'] == 'completed'
    assert result['result']['evidence_steps'] == ['observation-2']
    assert control._dispatch.await_count == 1


@pytest.mark.asyncio
async def test_changed_contract_blocks_worker_before_tool_execution(setup, monkeypatch):
    client, store, control = setup
    identifier = create(client).json()['run_id']
    record = store.get(identifier); record['contract_digest'] = 'changed'; store.put(identifier, record)
    await routes.execute_candidate(record)
    assert store.get(identifier)['status'] == 'blocked'
    control._dispatch.assert_not_awaited()


def test_cancel_fences_the_old_executor_and_preserves_evidence(setup):
    client, store, _ = setup
    identifier = create(client).json()['run_id']
    before = store.get(identifier)
    response = client.post(f'/api/v1/goals/{identifier}/cancel', headers={'Authorization':'Bearer owner-one'})
    assert response.status_code == 200 and response.json()['status'] == 'cancelled'
    assert not store.compare_and_put(identifier, before, {**before, 'status':'running'})
    assert store.get(identifier)['observations'] == []


def test_queue_limit_and_expired_status_are_explicit(setup):
    from datetime import datetime, timezone, timedelta
    client, store, _ = setup
    identifier = create(client).json()['run_id']
    expired = store.get(identifier)
    expired['deadline_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    store.put(identifier, expired)
    assert client.get('/api/v1/goals/'+identifier,headers={'Authorization':'Bearer owner-one'}).json()['status'] == 'timed_out'
    for index in range(16): store.put('queued-'+str(index), {'status':'queued'})
    assert create(client).status_code == 429


@pytest.mark.asyncio
async def test_changed_model_recipient_blocks_retained_goal_before_inference(setup, monkeypatch):
    client, store, control = setup
    identifier = create(client).json()['run_id']
    from backend.agentic_service import local_llm
    inference = AsyncMock()
    monkeypatch.setattr(local_llm, 'suggest_tool', inference)
    monkeypatch.setattr(local_llm, 'settings', lambda: ('openai', 'new-model', 'https://different.example', 10, {}))
    await routes.execute_candidate(store.get(identifier))
    assert store.get(identifier)['status'] == 'blocked'
    inference.assert_not_awaited()
    control._dispatch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected', [(503,'queued'), (403,'blocked')])
async def test_authority_outage_backs_off_but_rejection_blocks(setup, monkeypatch, status, expected):
    from fastapi import HTTPException
    from unittest.mock import Mock
    from backend.agentic_service import execution_grants
    client, store, control = setup
    identifier = create(client).json()['run_id']
    original = store.get(identifier)
    verify = Mock(side_effect=HTTPException(status))
    monkeypatch.setattr(execution_grants, 'verify_grant', verify)
    await routes.execute_candidate(original)
    updated = store.get(identifier)
    assert updated['status'] == expected
    assert updated['deadline_at'] == original['deadline_at']
    await routes.execute_candidate(updated)
    assert verify.call_count == 1
    control._dispatch.assert_not_awaited()
