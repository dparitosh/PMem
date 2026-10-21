import asyncio
import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from backend.agentic_service import goal_runner as goals


TOOLS = [{'id': 'read.primary', 'mutates': False, 'input_schema': {'type': 'object', 'additionalProperties': False,
    'properties': {'ontology_id': {'type': 'string'}}, 'required': ['ontology_id']}},
    {'id': 'read.alternative', 'mutates': False, 'input_schema': {'type': 'object', 'additionalProperties': False,
    'properties': {'ontology_id': {'type': 'string'}}, 'required': ['ontology_id']}}]


def record(**updates):
    return {'goal': 'Find the current ontology evidence', 'context': {'ontology_id': 'selected'},
            'scope': {'ontology_id': 'selected'}, 'plans': [], 'observations': [], 'decisions': 0,
            'max_decisions': 8, 'status': 'running',
            'deadline_at': (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(), **updates}


def action(tool_id, **inputs):
    return {'tool_id': tool_id, 'inputs': inputs}


@pytest.mark.asyncio
async def test_failed_read_is_remembered_and_a_different_allowed_tool_completes():
    decisions = [action('goal.plan', subtasks=['Read ontology evidence', 'Check another registered source on failure']),
                 action('read.primary', ontology_id='selected'),
                 action('read.alternative', ontology_id='selected'),
                 action('goal.complete', summary='Found ontology evidence.', evidence_steps=['observation-3'])]
    scratchpads, saved = [], []
    async def propose(tools, context):
        scratchpads.append(copy.deepcopy(context))
        return decisions.pop(0)
    async def dispatch(tool, inputs):
        if tool == 'read.primary': raise HTTPException(503, 'service unavailable')
        return {'iri': 'urn:Part'}
    async def save(value): saved.append(value)
    result = await goals.drive(record(), propose=propose, dispatch=dispatch, save=save, tools=TOOLS)
    assert result['status'] == 'completed'
    assert scratchpads[2]['observations'][0]['status'] == 'failed'
    assert any(item['observations'] and item['observations'][0]['status'] == 'dispatching' for item in saved)
    assert result['result']['evidence_steps'] == ['observation-3']


@pytest.mark.asyncio
async def test_resume_preserves_observations_deadline_and_never_replays_completed_reads():
    original = record(plans=[{'subtasks': ['Inspect']}], decisions=2,
        observations=[{'id': 'observation-2', 'tool_id': 'read.primary', 'status': 'completed', 'result': {'iri': 'urn:Part'},
                       'action_key': goals.fingerprint({'tool_id': 'read.primary', 'inputs': {'ontology_id': 'selected'}})}])
    dispatch = AsyncMock()
    proposal = AsyncMock(return_value=action('goal.complete', summary='Evidence retained.', evidence_steps=['observation-2']))
    result = await goals.drive(original, propose=proposal, dispatch=dispatch, save=AsyncMock(), tools=TOOLS)
    assert result['deadline_at'] == original['deadline_at']
    assert result['status'] == 'completed'
    dispatch.assert_not_awaited()


@pytest.mark.parametrize('proposal', [action('write.publish', ontology_id='selected'),
    action('read.primary', ontology_id='different'), action('read.primary'),
    action('goal.complete', summary='Invented', evidence_steps=['forged'])])
def test_writes_scope_changes_missing_scope_and_fabricated_evidence_are_held(proposal):
    with pytest.raises(ValueError):
        goals.validate_action(record(plans=[{'subtasks': ['Inspect']}]), proposal, TOOLS)


@pytest.mark.asyncio
async def test_authorization_failure_stops_instead_of_trying_another_identity():
    propose = AsyncMock(side_effect=[action('goal.plan', subtasks=['Inspect']), action('read.primary', ontology_id='selected')])
    result = await goals.drive(record(), propose=propose, dispatch=AsyncMock(side_effect=HTTPException(403)), save=AsyncMock(), tools=TOOLS)
    assert result['status'] == 'blocked'
    assert propose.await_count == 2


@pytest.mark.asyncio
async def test_invalid_plan_loop_stops_at_budget_without_dispatch():
    dispatch = AsyncMock()
    result = await goals.drive(record(max_decisions=3), propose=AsyncMock(return_value=action('write.publish')),
                               dispatch=dispatch, save=AsyncMock(), tools=TOOLS)
    assert result['status'] == 'budget_exhausted' and result['decisions'] == 3
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_deadline_blocks_all_calls():
    proposal, dispatch = AsyncMock(), AsyncMock()
    result = await goals.drive(record(deadline_at=datetime.now(timezone.utc).isoformat()),
                               propose=proposal, dispatch=dispatch, save=AsyncMock(), tools=TOOLS)
    assert result['status'] == 'timed_out'
    proposal.assert_not_awaited()
    dispatch.assert_not_awaited()


def test_registered_mutation_and_approval_bound_tools_are_not_available():
    tools = [{'id': 'read', 'mutates': False}, {'id': 'write', 'mutates': True}, {'id': 'held', 'mutates': False}]
    assert [tool['id'] for tool in goals.read_tools({'id': 'agent', 'tools': ['read', 'write', 'held']}, tools,
        lambda command: {'requires_approval': command['tool_id'] == 'held'})] == ['read']


def test_result_redaction_and_truncation_are_explicit(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'private-long-key')
    assert 'private-long-key' not in str(goals.bounded({'text': 'private-long-key'}))
    assert goals.bounded({'text': 'x' * 1000}, limit=100)['truncated'] is True


@pytest.mark.asyncio
async def test_transport_timeout_is_retained_and_allows_another_read():
    decisions = [action('goal.plan', subtasks=['Find evidence']), action('read.primary', ontology_id='selected'),
                 action('read.alternative', ontology_id='selected'),
                 action('goal.complete', summary='Alternative evidence found.', evidence_steps=['observation-3'])]
    async def propose(tools, context): return decisions.pop(0)
    async def dispatch(tool, inputs):
        if tool == 'read.primary': raise TimeoutError('read budget elapsed')
        return {'iri': 'urn:Part'}
    result = await goals.drive(record(), propose=propose, dispatch=dispatch, save=AsyncMock(), tools=TOOLS)
    assert result['status'] == 'completed'
    assert result['observations'][0]['error_code'] == 'read_transport_unavailable'


def test_truncated_observation_cannot_support_completion():
    state = record(plans=[{'subtasks': ['Inspect']}], observations=[{'id':'observation-2', 'status':'completed',
        'result':{'truncated':True, 'excerpt':'partial'}}])
    with pytest.raises(ValueError):
        goals.validate_action(state, action('goal.complete', summary='Unsupported', evidence_steps=['observation-2']), TOOLS)


def test_source_target_aliases_cannot_be_used_to_escape_selected_ontologies():
    state = record(scope={'source_ontology_id':'selected', 'target_ontology_id':'other-selected'}, plans=[{'subtasks':['Inspect']}])
    with pytest.raises(ValueError):
        goals.validate_action(state, action('read.primary', ontology_id='outside'), TOOLS)
    assert goals.validate_action(state, action('read.primary', ontology_id='other-selected'), TOOLS)[0] == 'read.primary'
    assert goals.selected_scope({'ontology_id':None}) == {}
    with pytest.raises(ValueError): goals.selected_scope({'source_ontology_ids':'bad'})
