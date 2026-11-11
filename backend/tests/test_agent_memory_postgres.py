"""Agent memory behaviour on PostgreSQL (short-term, long-term, context), with an in-memory registry double."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.Services.agent_memory_service import AgentMemoryService as Memory


class FakeRegistry:
    """Mirrors the PostgresRegistry methods the memory service uses, backed by one shared dict per namespace."""
    namespaces: dict = {}

    def __init__(self, namespace):
        self.namespace = namespace
        self.items = FakeRegistry.namespaces.setdefault(namespace, {})

    def get(self, key):
        return self.items.get(key)

    def put(self, key, value):
        self.items[key] = value
        return value

    def put_many(self, values):
        self.items.update(values)
        return values

    def prefix_items(self, prefix, *, limit=1000):
        assert prefix
        return {k: v for k, v in sorted(self.items.items()) if k.startswith(prefix)}

    def prefix_latest(self, prefix, *, limit=100):
        rows = [(k, v) for k, v in sorted(self.items.items(), reverse=True) if k.startswith(prefix)]
        return rows[:limit]

    def delete_prefix(self, prefix):
        assert prefix
        for key in [k for k in self.items if k.startswith(prefix)]:
            del self.items[key]

    def keys_expired_before(self, *, scope, field, cutoff, limit=500):
        return [k for k, v in sorted(self.items.items())
                if v.get('scope') == scope and str(v.get(field, '')) < cutoff and not v.get('legal_hold')][:limit]


class Unavailable(FakeRegistry):
    def __getattribute__(self, name):
        if name in {'get', 'put', 'put_many', 'prefix_items', 'prefix_latest', 'delete_prefix', 'keys_expired_before'}:
            def fail(*args, **kwargs):
                raise ConnectionError('postgres down')
            return fail
        return object.__getattribute__(self, name)


@pytest.fixture
def memory(monkeypatch):
    FakeRegistry.namespaces = {}
    monkeypatch.setenv('AGENT_MEMORY_ENABLED', 'true')
    monkeypatch.setenv('AGENT_MEMORY_SCOPE', 'tcs:nexus')
    monkeypatch.setenv('AGENT_SESSION_MAX_SECONDS', '86400')
    Memory._health.clear()
    import backend.mesh_store as mesh_store
    monkeypatch.setattr(mesh_store, 'PostgresRegistry', FakeRegistry)
    return Memory


def _turn(memory, session, user, assistant, graph_context=None):
    assert memory.record_chat_turn(session_id=session, user_message=user, assistant_response=assistant, graph_context=graph_context)


def test_disabled_memory_is_a_noop(monkeypatch, memory):
    monkeypatch.setenv('AGENT_MEMORY_ENABLED', 'false')
    assert memory.record_chat_turn(session_id='s', user_message='q', assistant_response='a') is False
    assert memory.recent_context('s') == {'enabled': False, 'messages': [], 'facts': []}
    assert FakeRegistry.namespaces == {}


def test_short_term_turns_are_stored_and_recalled_newest_first(memory):
    _turn(memory, 's1', 'first question', 'first answer')
    _turn(memory, 's1', 'second question', 'second answer')
    context = memory.recent_context('s1', limit=3)
    assert context['status'] == 'available'
    assert [m['text'] for m in context['messages']] == ['second answer', 'second question', 'first answer']
    assert [m['role'] for m in context['messages']] == ['assistant', 'user', 'assistant']


def test_recall_is_bounded_and_session_bound(memory):
    _turn(memory, 's1', 'a', 'b')
    _turn(memory, 's2', 'other user', 'other answer')
    context = memory.recent_context('s1', limit=1)
    assert [m['text'] for m in context['messages']] == ['b']
    assert all('other' not in m['text'] for m in memory.recent_context('s1')['messages'])


def test_memory_is_isolated_by_scope(memory, monkeypatch):
    _turn(memory, 's1', 'tcs question', 'tcs answer')
    monkeypatch.setenv('AGENT_MEMORY_SCOPE', 'other:project')
    assert memory.recent_context('s1')['messages'] == []


def test_expired_turns_are_not_recalled(memory):
    _turn(memory, 's1', 'old', 'old answer')
    key = next(k for k in FakeRegistry.namespaces['agent_memory_short'])
    FakeRegistry.namespaces['agent_memory_short'][key]['created_at'] = '2000-01-01T00:00:00.000000Z'
    assert memory.recent_context('s1')['messages'] == []


def test_reasoning_traces_are_context_memory_and_deleted_with_the_session(memory):
    memory.record_reasoning_trace(session_id='s1', task='summarise', tool_name='graph.search', input_payload={'q': 'x'}, result_summary={'n': 2})
    assert len(FakeRegistry.namespaces['agent_memory_trace']) == 1
    assert memory.delete_session('s1') is True
    assert FakeRegistry.namespaces['agent_memory_trace'] == {}
    assert FakeRegistry.namespaces['agent_memory_short'] == {}


def test_only_approved_bridge_mappings_become_long_term_facts(memory):
    memory.record_semantic_bridge_mappings(
        ontology_id='ap242', import_task_id='import-1', task_id='task-1',
        mappings=[
            {'source_term': 'Hole', 'ontology_term': 'Feature', 'selected_for_apply': True, 'confidence': 0.9},
            {'source_term': 'Pending', 'ontology_term': 'Feature'},
        ])
    facts = memory.semantic_bridge_facts('ap242')
    assert [f['source'] for f in facts] == ['Hole']
    assert facts[0]['lifecycle_status'] == 'approved'


def test_fact_reads_require_a_resolved_ontology(memory):
    memory.record_semantic_bridge_mappings(ontology_id='ap242', import_task_id='i', task_id='t',
                                           mappings=[{'source_term': 'A', 'ontology_term': 'B', 'approvedByUser': True}])
    assert memory.semantic_bridge_facts('') == []
    assert memory.semantic_bridge_facts('other') == []


def test_facts_are_isolated_by_scope(memory, monkeypatch):
    memory.record_semantic_bridge_mappings(ontology_id='ap242', import_task_id='i', task_id='t',
                                           mappings=[{'source_term': 'A', 'ontology_term': 'B', 'approvedByUser': True}])
    monkeypatch.setenv('AGENT_MEMORY_SCOPE', 'other:project')
    assert memory.semantic_bridge_facts('ap242') == []


def test_superseded_and_expired_facts_are_not_reused(memory):
    memory.record_semantic_bridge_mappings(ontology_id='ap242', import_task_id='i', task_id='t',
                                           mappings=[{'source_term': 'A', 'ontology_term': 'B', 'approvedByUser': True}])
    fact = next(iter(FakeRegistry.namespaces['agent_memory_fact'].values()))
    fact['superseded_by'] = 'newer'
    assert memory.semantic_bridge_facts('ap242') == []
    fact.pop('superseded_by')
    fact['valid_until'] = '2000-01-01T00:00:00.000000Z'
    assert memory.semantic_bridge_facts('ap242') == []


def test_retention_removes_expired_sessions_but_keeps_legal_holds(memory):
    _turn(memory, 'old-session', 'q', 'a')
    _turn(memory, 'held-session', 'q', 'a')
    past = (datetime.now(timezone.utc) - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    sessions = FakeRegistry.namespaces['agent_memory_session']
    for key, value in sessions.items():
        value['updated_at'] = past
        if value['session_ref'] == 'held-session':
            value['legal_hold'] = True
    assert memory.prune_expired_sessions(retention_days=30) == 1
    remaining = {v['session_ref'] for v in sessions.values()}
    assert remaining == {'held-session'}
    assert memory.recent_context('held-session')['messages']


def test_postgres_outage_is_reported_without_breaking_chat(memory):
    with patch('backend.mesh_store.PostgresRegistry', Unavailable):
        assert memory.record_chat_turn(session_id='s', user_message='q', assistant_response='a') is False
        context = memory.recent_context('s')
        assert context['status'] == 'unavailable'
        assert context['messages'] == []
        assert memory.delete_session('s') is False
        assert memory.status(probe=True)['status'] == 'unavailable'


def test_touched_nodes_are_read_from_the_frontend_graph_snapshot():
    nodes = Memory._extract_touched_nodes({
        'selectedNode': {'elementId': 'selected', 'name': 'Selected'},
        'visibleGraph': {'nodes': [{'elementId': 'visible', 'name': 'Visible'}, {'elementId': 'selected', 'name': 'Duplicate'}]},
        'searchResults': {'nodes': [{'elementId': 'search', 'label': 'Search'}]},
    })
    assert nodes == [
        {'element_id': 'selected', 'label': 'Selected'},
        {'element_id': 'visible', 'label': 'Visible'},
        {'element_id': 'search', 'label': 'Search'},
    ]
