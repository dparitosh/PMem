"""Business evidence boundaries without modifying customer databases."""
from unittest.mock import Mock, patch
import pytest

from backend.graph_service import business_context, document_evidence
from backend.Services.graph_view_service import GraphViewService
from backend.depo_platform.neo4j_setup import REQUIRED_INDEXES, verify_indexes
from backend.agentic_service.goal_runner import SCOPE_KEYS
from backend.graph_service import context_router


def node(identity, scope='selected', kind='Part'):
    return {'elementId': identity, 'labels': ['OntologyResource'], 'properties': {
        'ontology_id': scope, 'label': identity,
        'rdf_types': ['https://depo.example.org/ceim/0.1/' + kind]}}


def test_context_keeps_connected_business_objects_and_recorded_paths(monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    root, neighbor, unrelated, other_scope = node('root'), node('neighbor'), node('unrelated'), node('other', 'different')
    edges = [{'elementId': 'trace', 'start': 'root', 'end': 'neighbor', 'type': 'TRACE_TO'},
             {'elementId': 'outside', 'start': 'root', 'end': 'other', 'type': 'SEMANTICALLY_MAPPED_TO'}]
    publisher = Mock(_session_rows=Mock(return_value=[root]))
    with patch.object(GraphViewService, 'get_traversal_slice', return_value={'nodes': [root, neighbor, unrelated, other_scope], 'relationships': edges}):
        result = business_context.retrieve(publisher, node_id='root', ontology_id='selected')
    assert [n['elementId'] for n in result['nodes']] == ['root', 'neighbor']
    assert result['inclusion']['neighbor']['path_relationship_ids'] == ['trace']
    assert result['relationships'][0]['evidence_kind'] == 'source_reference'
    assert result['view']['semantic_entailment_verified'] is False
    assert result['view']['whole_graph_complete'] is False


def test_schema_term_is_not_a_business_root(monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    publisher = Mock(_session_rows=Mock(return_value=[node('schema', kind='NotABusinessType')]))
    with pytest.raises(ValueError, match='business instance'):
        business_context.retrieve(publisher, node_id='schema')


def test_missing_evidence_index_is_explicit(monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    publisher = Mock(_session_rows=Mock(return_value=[]))
    result = document_evidence.retrieve(publisher, query='product quality')
    assert result['status'] == 'not_indexed'
    assert result['evidence'] == []
    assert result['retrieval']['whole_source_complete'] is False
    assert publisher._session_rows.call_count == 1


def test_wrong_index_type_cannot_pass_bootstrap_validation():
    rows = [{'name': name, 'type': 'FULLTEXT' if isinstance(label,tuple) else 'TEXT' if 'resource_search' in name else 'RANGE',
             'state': 'ONLINE', 'labelsOrTypes': list(label) if isinstance(label,tuple) else [label], 'properties': properties}
            for name, (label, properties) in REQUIRED_INDEXES.items()]
    verify_indexes(rows)
    rows[0]['type'] = 'RANGE'
    with pytest.raises(RuntimeError, match='performance indexes'):
        verify_indexes(rows)


def test_selected_business_identity_is_a_pinned_agent_scope():
    assert 'node_id' in SCOPE_KEYS


def test_canonical_rdf_process_is_not_hidden_by_storage_label():
    with patch.object(context_router, '_find_node', return_value={'id': 'part', 'name': 'Part'}), patch.object(
        context_router, '_neighbors', return_value=[{'id': 'process', 'name': 'Manufacture',
        'labels': ['OntologyResource'], 'rdf_types': ['https://depo.example.org/ceim/0.1/Process']}]
    ):
        result = context_router._manufacturing_context_result({'node_id': 'part'})
    assert result['direct_processes'][0]['process_name'] == 'Manufacture'


def test_generic_storage_labels_do_not_boost_similarity():
    with patch.object(context_router, '_find_node', return_value={'id': 'part', 'name': 'Motor', 'labels': ['OntologyResource']}), patch.object(
        context_router.publisher, 'search', return_value={'nodes':[{'elementId': 'other', 'properties':{'label':'Motor'}, 'labels': ['OntologyResource']}]}
    ):
        result = context_router._similar_parts_result({'node_id': 'part'})
    assert result['similar_parts'][0]['score_evidence']['graph_type_match'] is False
    assert result['similar_parts'][0]['similarity_score'] == 75


def test_document_query_uses_safe_tokens_and_explicit_scope(monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    publisher = Mock(_session_rows=Mock(side_effect=[[{'state': 'ONLINE'}], []]))
    result = document_evidence.retrieve(publisher, query='motor OR *:*', ontology_id='selected')
    assert result['status'] == 'no_evidence'
    query = publisher._session_rows.call_args.kwargs
    assert query['scope'] == 'selected'
    assert query['lucene_query'] == '"motor"'


@pytest.mark.asyncio
async def test_companion_includes_connected_nonlexical_object(monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from backend.agentic_service import companion, companion_context
    monkeypatch.setenv('COMPANION_LLM_ENABLED', 'false')
    monkeypatch.setattr(companion_context, 'mapping_context', AsyncMock(return_value={'evidence': [], 'status': 'not_requested'}))
    monkeypatch.setattr(companion_context, 'page_context', AsyncMock(return_value={'evidence': [], 'status': 'not_requested'}))
    monkeypatch.setattr(companion_context, 'document_context', AsyncMock(return_value={'evidence': [], 'status': 'no_evidence'}))
    root, neighbor = node('root'), node('neighbor')
    root['properties']['label'] = 'Motor'
    neighbor['properties']['label'] = 'Acceptance requirement'
    edge = {'elementId': 'trace', 'start': 'root', 'end': 'neighbor', 'type': 'TRACE_TO'}
    connected = {'nodes': [root, neighbor], 'relationships': [edge],
        'inclusion': {'neighbor': {'reason': 'source_reference', 'path_relationship_ids': ['trace']}}}
    monkeypatch.setattr(companion_context, 'business_context', AsyncMock(return_value=(connected, 'http://graph/business-context')))
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'nodes': [root], 'relationships': [], 'view': {'truncated': False}}))
    monkeypatch.setattr(companion.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=transport, **kwargs))
    result = await companion.KnowledgeCompanion().ask('Motor', headers={}, ontology_id='selected', page='graph')
    resources = {item['resource_id'] for item in result['evidence'] if item['evidence_type'] == 'graph_resource'}
    assert resources == {'root', 'neighbor'}
    assert result['retrieval']['business_context_status'] == 'available'
    assert result['retrieval']['semantic_entailment_verified'] is False
