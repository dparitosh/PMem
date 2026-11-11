"""Registry discovery, permission metadata and snapshot boundaries."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.agentic_service.app import app
from backend.agentic_service import router
from backend.agentic_service.catalog_contract import validate_catalog
from backend.agentic_service.catalog_loader import load_catalog
from backend.agentic_service.registry_view import registry_view


@pytest.fixture
def access(monkeypatch):
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE', 'environment')
    monkeypatch.setenv('GRAPH_READ_TOKEN', 'registry-reader-fixture-token-000000000')
    monkeypatch.delenv('GRAPH_READ_TOKEN_EXPIRES_AT', raising=False)
    monkeypatch.delenv('DEPO_TOKEN_EXPIRES_AT', raising=False)
    return TestClient(app), {'Authorization': 'Bearer registry-reader-fixture-token-000000000'}


@pytest.mark.parametrize('path', ['agents', 'tools', 'mcp-servers', 'workflows', 'agent-registry', 'agent-architecture'])
def test_anonymous_discovery_is_rejected_before_catalog_is_read(access, monkeypatch, path):
    client, _ = access
    read = Mock(side_effect=AssertionError('Unauthenticated catalog read'))
    monkeypatch.setattr(router.catalog, 'read', read)
    assert client.get('/api/v1/'+path).status_code == 403
    read.assert_not_called()


@pytest.mark.parametrize('path,payload', [('plans', {'agent_id':'graph-analyst','tool_id':'graph.analytics'}),
                                       ('workflow-plans', {'workflow_id':'engineering-governed-publish'})])
def test_anonymous_planning_cannot_disclose_tool_definitions(access, path, payload):
    client, _ = access
    assert client.post('/api/v1/'+path, json=payload).status_code == 403


def test_registry_is_safe_and_single_snapshot(access, monkeypatch):
    client, headers = access
    source = load_catalog()
    source['agents'][0]['system_prompt'] = 'private-registry-prompt'
    source['agents'][0]['private_configuration'] = 'private-agent-extension'
    source['workflows'][0]['system_prompt'] = 'private-workflow-extension'
    source['mcp_servers'][0].update(command='private-launch-command', args=['private-launch-argument'], env={'PRIVATE':'private-launch-environment'})
    original = copy.deepcopy(source)
    read = Mock(return_value=source)
    monkeypatch.setattr(router.catalog, 'read', read)
    response = client.get('/api/v1/agent-registry', headers=headers)
    assert response.status_code == 200
    body = response.json()
    read.assert_called_once_with()
    assert body['registry']['agent_count'] == len(body['agents']) == 28
    assert body['registry']['tool_count'] == len(body['tools']) == 62
    assert body['registry']['readiness'] == 'not_verified'
    assert len(body['registry']['revision']) == 64
    for value in ('private-registry-prompt', 'private-agent-extension', 'private-workflow-extension', 'private-launch-command', 'private-launch-argument', 'private-launch-environment'):
        assert value not in json.dumps(body)
    assert source == original
    for row in body['agents']:
        assert row['description'] != row['name']


def test_digest_tracks_prompt_changes_without_exposing_prompt():
    source = load_catalog()
    first = registry_view(source)
    assert registry_view(source)['registry']['revision'] == first['registry']['revision']
    source['agents'][0]['system_prompt'] += ' Additional domain constraint.'
    assert registry_view(source)['registry']['revision'] != first['registry']['revision']


@pytest.mark.parametrize('bad', ['false', 0, None, [], {}])
def test_non_boolean_mutation_flags_are_rejected(bad):
    source = load_catalog()
    source['tools'][0]['mutates'] = bad
    with pytest.raises(ValueError, match='boolean'):
        validate_catalog(source)


@pytest.mark.parametrize('kind', ['agents', 'steps'])
def test_non_boolean_approval_flags_are_rejected(kind):
    source = load_catalog()
    item = source['agents'][0] if kind == 'agents' else source['workflows'][0]['steps'][0]
    item['approval_required'] = 'false'
    with pytest.raises(ValueError, match='boolean'):
        validate_catalog(source)


@pytest.mark.parametrize('broken', ['missing', 'invalid-json'])
def test_unavailable_catalog_has_actionable_sanitized_503(access, monkeypatch, tmp_path, broken):
    client, headers = access
    path = tmp_path/'private-customer-directory'/'catalog.json'
    if broken == 'invalid-json':
        path.parent.mkdir()
        path.write_text('{invalid json')
    monkeypatch.setattr(router.catalog, 'path', path)
    response = client.get('/api/v1/agent-registry', headers=headers)
    assert response.status_code == 503
    assert 'verify the configured catalog' in response.json()['detail']
    assert 'private-customer-directory' not in response.text
    assert response.headers.get('x-request-id')


def test_role_and_tool_plan_use_one_catalog_generation(monkeypatch):
    source = load_catalog()
    read = Mock(return_value=source)
    monkeypatch.setattr(router.catalog, 'read', read)
    result = router.plan({'agent_id':'graph-analyst', 'tool_id':'graph.analytics'})
    assert result['valid']
    read.assert_called_once_with()


def test_workflow_plan_uses_one_catalog_generation(monkeypatch):
    source = load_catalog()
    read = Mock(return_value=source)
    monkeypatch.setattr(router.catalog, 'read', read)
    assert router.workflow_plan({'workflow_id':'engineering-governed-publish'})['steps']
    read.assert_called_once_with()


def test_read_goal_selection_uses_one_catalog_generation(monkeypatch):
    from backend.agentic_service.goal_routes import selected
    source = load_catalog()
    read = Mock(return_value=source)
    monkeypatch.setattr(router.catalog, 'read', read)
    agent, tools = selected('graph-analyst')
    assert agent['id'] == 'graph-analyst' and tools
    read.assert_called_once_with()
