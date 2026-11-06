"""Semantic memory continuity without live models or databases."""
import ast
import json
from pathlib import Path
from unittest.mock import patch
from backend.agentic_service.companion_memory import retrieval_query
from backend.Services.agent_memory_service import AgentMemoryService as Memory


def test_followup_keeps_resolved_subject_across_three_turns():
    scope = {'ontology': 'ap242', 'page': 'graph', 'node_id': 'housing'}
    turns = [{'user_request': 'And its properties?',
              'resolved_query': 'Show requirements for Housing And its properties?',
              'answerable': True, 'graph_context': scope}]
    result = retrieval_query('What about its PMI?', turns, scope)
    assert 'Housing' in result
    assert retrieval_query('What about its PMI?', turns, {**scope, 'node_id': 'shaft'}) == 'What about its PMI?'


def test_failed_answer_cannot_become_subject_memory():
    scope = {'page': 'graph'}
    turns = [{'user_request': 'Failed subject', 'answerable': False, 'graph_context': scope},
             {'user_request': 'Housing', 'answerable': True, 'graph_context': scope}]
    result = retrieval_query('its properties', turns, scope)
    assert result == 'Housing its properties'


def test_optional_graph_memory_retains_only_projected_context(monkeypatch):
    monkeypatch.setenv('AGENT_MEMORY_ENABLED', 'true')
    monkeypatch.setenv('AGENT_MEMORY_SCOPE', 'test:memory')
    with patch.object(Memory, 'ensure_schema', return_value={'ensured': True}), patch.object(Memory, '_query', return_value=[]) as query:
        assert Memory.record_chat_turn(session_id='s', user_message='Housing', assistant_response='Observed record',
            graph_context={'ontology': 'ap242', 'node_id': 'n', 'run_id': 'r', 'reconciliation_id': 'e',
                           'password': 'do-not-retain', 'nodes': [{'api_key': 'secret'}]})
    params = query.call_args.args[1]
    retained = json.loads(params['context_json'])
    assert retained == {'ontology': 'ap242', 'node_id': 'n', 'run_id': 'r', 'reconciliation_id': 'e'}
    assert 'do-not-retain' not in params['context_json']
    assert 'a.context_json = $context_json' in query.call_args.args[0]


def test_companion_wires_scope_to_optional_memory_and_retains_resolved_query():
    tree = ast.parse(Path('backend/agentic_service/router.py').read_text(encoding='utf-8'))
    owner = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_companion_chat')
    call = next(n for n in ast.walk(owner) if isinstance(n, ast.Call) and any(
        isinstance(arg, ast.Attribute) and arg.attr == 'record_chat_turn' for arg in n.args))
    assert any(k.arg == 'graph_context' and isinstance(k.value, ast.Name) and k.value.id == 'selected_context' for k in call.keywords)
    assert any(isinstance(n, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == 'resolved_query' for k in n.keys) for n in ast.walk(owner))


def test_event_review_context_passes_actual_chat_request_validation():
    import pytest
    from pydantic import ValidationError
    from backend.agentic_service.chat_request import ChatRequest
    body=ChatRequest(message='Explain this review',graph_context={'page':'data-flow','reconciliation_id':'review-one'})
    assert body.model_dump()['graph_context']['reconciliation_id']=='review-one'
    for other in ('run_id','product_id'):
        with pytest.raises(ValidationError):
            ChatRequest(message='Explain',graph_context={'reconciliation_id':'review-one',other:'other'})
