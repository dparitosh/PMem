from fastapi.testclient import TestClient
from mbse_plugin.app import app
from mbse_plugin.teamcenter_smw.mapping import MappingConfig, preview
import pytest


def test_mapping_quality_and_revision_contract():
    config = dict(id='test', version='1', source_namespace='model', objects={'T': {'target_type': 'Resource', 'fields': {'data.name': 'name'}, 'required': ['data.name']}}, relationships={'contains': 'HAS_PART'}, identity_mode='source_revision')
    c = MappingConfig(**config)
    records = [{'uid': 'a', 'type': 'T', 'revision': 'A', 'data': {'name': 'one'}}, {'uid': 'a', 'type': 'T', 'revision': 'B', 'data': {'name': 'two'}}]
    result = preview(c, records, [{'source': 'a', 'source_revision': 'A', 'target': 'a', 'target_revision': 'B', 'type': 'contains'}])
    assert len(result['relationships']) == 1
    assert result['entities'][0]['id'] != result['entities'][1]['id']
    assert preview(c, [], [])['status'] == 'empty'
    records[0]['data']['name'] = '   '
    assert preview(c, records, [])['status'] == 'invalid'
    records[0]['deleted'] = True
    assert preview(c, records, [])['quality_errors'][0]['rule'] == 'deletion_requires_live_reconciliation'
    config['objects']['T']['fields']['alias'] = 'name'
    with pytest.raises(ValueError, match='share a target'):
        MappingConfig(**config)


def test_offline_mapping(monkeypatch):
    monkeypatch.setenv('MBSE_PLUGIN_TOKEN', 'test')
    client = TestClient(app)
    headers = {'Authorization': 'Bearer test'}
    assert client.get('/teamcenter-smw/template').status_code == 401
    mapping = client.get('/teamcenter-smw/template', headers=headers).json()
    body = {'mapping': mapping, 'records': [{'uid': 'r', 'type': 'ExampleRequirement', 'name': 'Safety'}]}
    result = client.post('/teamcenter-smw/preview', headers=headers, json=body).json()
    assert result['status'] == 'draft_preview'
    assert result['publishable'] is False
    assert result['entities'][0]['ceim_type'] == 'Requirement'
    body['links'] = [{'source': 'r', 'target': 'missing', 'type': 'ExampleSatisfies'}]
    assert client.post('/teamcenter-smw/preview', headers=headers, json=body).json()['status'] == 'invalid'
    mapping['connector_enabled'] = True
    assert client.post('/teamcenter-smw/preview', headers=headers, json=body).status_code == 422
