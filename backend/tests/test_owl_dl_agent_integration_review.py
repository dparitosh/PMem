"""Post-integration review: real reasoner/API plus explicit known-gap repros.

No LLM calls, live registry writes or graph publications are performed.
Regression cases cover the previously confirmed integration defects.
"""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from backend.agentic_service import goal_runner
from backend.mesh_store import InMemoryRegistry
from backend.ontology_service import owl_dl
from backend.ontology_service.catalog import OntologyCatalog


TOOL = {'id': 'ontology.consistency.check', 'mutates': False,
        'input_schema': {'type': 'object', 'additionalProperties': False,
                         'properties': {'ontology_id': {'type': 'string'}}, 'required': ['ontology_id']}}


def goal(**updates):
    return {'goal': 'Check OWL-DL consistency for the selected ontology',
            'context': {'ontology_id': 'selected'}, 'scope': {'ontology_id': 'selected'},
            'plans': [{'subtasks': ['Check the selected retained ontology']}], 'observations': [],
            'status': 'running', 'decisions': 0, 'max_decisions': 8,
            'deadline_at': (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat(), **updates}


def test_unknown_reasoner_evidence_cannot_support_a_consistency_success_claim():
    record = goal(observations=[{'id': 'observation-1', 'tool_id': TOOL['id'], 'status': 'completed',
                               'inputs': {'ontology_id': 'selected'},
                               'result': {'ontology_id': 'selected', 'status': 'unknown',
                                          'reason': 'unresolved_imports', 'consistency_verified': False}}])
    with pytest.raises(ValueError):
        goal_runner.validate_action(record, {'tool_id': 'goal.complete', 'inputs': {
            'summary': 'The selected ontology is verified OWL-DL consistent.', 'evidence_steps': ['observation-1']}}, [TOOL])


def test_consistency_tool_requires_an_explicit_ontology_in_the_goal_context():
    with pytest.raises(ValueError):
        goal_runner.validate_action(goal(context={}, scope={}),
                                    {'tool_id': TOOL['id'], 'inputs': {'ontology_id': 'model-chosen'}}, [TOOL])


def test_consistency_tool_cannot_change_an_existing_selected_ontology():
    with pytest.raises(ValueError, match='scope|selected|sources'):
        goal_runner.validate_action(goal(), {'tool_id': TOOL['id'], 'inputs': {'ontology_id': 'other'}}, [TOOL])


def test_real_consistency_api_is_read_authenticated_and_retains_hash_bound_evidence(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.ontology_service.app import app
    from backend.ontology_service.modeling_router import _modeling_identity
    from backend.ontology_service import router
    from backend.depo_platform import ontology_maintenance
    assert owl_dl.capabilities()['available'], 'Verified local Java reasoner is required for this review'
    store = InMemoryRegistry()
    content = b'@prefix owl:<http://www.w3.org/2002/07/owl#> . <urn:review:A> a owl:Class .'
    monkeypatch.setattr(router, 'catalog', SimpleNamespace(
        read_artifact=lambda _: ({'original_filename': 'review.ttl'}, content),
        _parse_ontology=OntologyCatalog._parse_ontology))
    monkeypatch.setattr(router, 'PostgresRegistry', lambda namespace: store)
    monkeypatch.setattr(ontology_maintenance, 'ontology_operation', lambda **kwargs: nullcontext())
    original = dict(app.dependency_overrides)
    def denied():
        from fastapi import HTTPException
        raise HTTPException(403, 'review read access denied')
    try:
        app.dependency_overrides[_modeling_identity] = denied
        client = TestClient(app)  # No lifespan/background workers are started.
        assert client.get('/api/v1/ontologies/selected/consistency').status_code == 403
        app.dependency_overrides[_modeling_identity] = lambda: 'review-reader'
        response = client.get('/api/v1/ontologies/selected/consistency')
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['status'] == 'consistent' and result['consistency_verified'] is True
        assert result['ontology_id'] == 'selected'
        assert result['foundation']['included'] is True
        assert result['foundation']['bundle_sha256'] and result['artifact_sha256'] and result['evidence_id']
        assert result['graph_publication_performed'] is False
        assert store.get(result['evidence_id'])['status'] == 'consistent'
        cached = client.get('/api/v1/ontologies/selected/consistency').json()
        assert cached['cached'] is True and cached['evidence_id'] == result['evidence_id']
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def test_unresolved_imports_remain_unknown_and_reuse_unchanged_evidence(monkeypatch):
    content = b'@prefix owl:<http://www.w3.org/2002/07/owl#> . <urn:o> a owl:Ontology ; owl:imports <https://unapproved.invalid/model> .'
    parse = Mock(wraps=OntologyCatalog._parse_ontology)
    catalog = SimpleNamespace(read_artifact=lambda _: ({'original_filename':'review.ttl'}, content), _parse_ontology=parse)
    store = InMemoryRegistry()
    first = owl_dl.inspect_retained('selected', catalog, store)
    second = owl_dl.inspect_retained('selected', catalog, store)
    assert first['status'] == second['status'] == 'unknown'
    assert first['consistency_verified'] is second['consistency_verified'] is False
    assert first['reason'] == 'unresolved_imports'
    assert parse.call_count == 1 and second['cached'] is True


def test_large_reasoner_payload_preserves_structured_verdict_in_agent_budget_projection():
    evidence = {'status': 'consistent', 'consistency_verified': True,
                'ontology_id': 'selected', 'artifact_sha256': 'a'*64,
                'foundation': {'bundle_sha256': 'b'*64},
                'classification': [{'subject':'urn:large:'+str(i)+'x'*150, 'object':'urn:parent:'+'y'*150} for i in range(200)]}
    result = goal_runner.bounded(evidence)
    assert result['truncated'] is True
    assert result.get('consistency_verified') is True
    assert result.get('artifact_sha256') == evidence['artifact_sha256']


@pytest.mark.asyncio
async def test_generic_page_context_leaves_selected_semantic_questions_to_the_dedicated_route(monkeypatch):
    from backend.agentic_service import companion_context
    from unittest.mock import AsyncMock
    read = AsyncMock()
    monkeypatch.setattr(companion_context, '_read_json', read)
    result = await companion_context.page_context('Is the selected ontology logically consistent?',
        page='ontology', headers={}, ontology_id='selected')
    assert result == {'evidence': [], 'status': 'not_requested'}
    read.assert_not_called()
