from unittest.mock import patch
import pytest
from fastapi import HTTPException
from backend.graph_service import context_router as api


def node(identity, name, source):
    return {'elementId': identity, 'labels': ['Part'], 'properties': {'name': name, 'ontology_id': source}}


def test_bounded_business_search_exposes_selectable_identities_without_picking_one():
    graph = {'nodes': [node('revision-1', 'Induction Motor', 'plant-a'), node('revision-2', 'Induction Motor', 'plant-b')], 'view': {'truncated': True}}
    with patch.object(api.publisher, 'search', return_value=graph) as search:
        result = api.resolve_recommendation_object({'part_name': 'induction motor'})
        assert result['truncated'] is True
        assert result['matches'] == [
            {'node_id': 'revision-1', 'name': 'Induction Motor', 'scope': {'ontology_id': 'plant-a'}},
            {'node_id': 'revision-2', 'name': 'Induction Motor', 'scope': {'ontology_id': 'plant-b'}},
        ]
        assert search.call_args.kwargs['business_only'] is True
        assert search.call_args.kwargs['limit'] == 20
        with pytest.raises(HTTPException) as failure:
            api._find_node('Induction Motor')
        assert failure.value.status_code == 409


def test_resolver_retains_selected_scope_and_empty_results_are_explicit():
    with patch.object(api.publisher, 'search', return_value={'nodes': [], 'view': {}}) as search:
        assert api.resolve_recommendation_object({'part_name': 'Motor', 'scope': {'ontology_id': 'plant'}}) == {'matches': [], 'truncated': False}
        assert search.call_args.kwargs['ontology_id'] == 'plant'


def test_exact_business_name_uses_name_property():
    with patch.object(api.publisher, 'search', return_value={'nodes': [node('part-1', 'Motor', 'plant')], 'view': {}}):
        assert api._find_node('Motor')['name'] == 'Motor'


def test_process_context_distinguishes_unassessed_categories_from_measured_zero():
    with patch.object(api, '_find_node', return_value={'id': 'part', 'name': 'Motor'}), patch.object(api, '_neighbors', return_value=[]):
        result = api._manufacturing_context_result({'part_name': 'Motor', 'node_id': 'part'})
    assert result['process_summary']['total_direct'] == 0
    assert result['process_summary']['total_instances'] is None
    assert result['process_summary']['total_related'] is None
    assert result['assessment'] == {'direct_processes': 'assessed', 'process_instances': 'not_assessed', 'related_processes': 'not_assessed', 'type_summary': 'not_assessed'}


@pytest.mark.parametrize('name', ['', 'x' * 501])
def test_resolver_rejects_invalid_names_without_search(name):
    with patch.object(api.publisher, 'search') as search:
        with pytest.raises(HTTPException) as failure:
            api.resolve_recommendation_object({'part_name': name})
        assert failure.value.status_code == 422
        search.assert_not_called()
