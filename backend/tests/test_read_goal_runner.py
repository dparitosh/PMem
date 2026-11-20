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


def test_graph_prompt_projection_preserves_measurements_identities_and_links():
    source={'root_node_id':'a','nodes':[
        {'elementId':'a','properties':{'label':'Test A','temperature':76,'temperature_unit':'degC','password':'excluded','dataOrigin':'ODS scenario'}},
        {'elementId':'b','properties':{'label':'Option B','estimatedIncrementalCost':8,'cost_unit':'USD/unit','dataOrigin':'ODS scenario'}}],
        'relationships':[{'elementId':'edge-1','start':'b','end':'a','type':'VERIFIED_BY','properties':{'predicate':'urn:verifiedBy'}}],
        'view':{'truncated':False}}
    projected=goals.graph_context_prompt(source)
    assert projected['nodes'][0]['properties']['temperature']=='76'
    assert projected['nodes'][0]['properties']['temperature_unit']=='degC'
    assert projected['nodes'][1]['properties']['estimatedIncrementalCost']=='8'
    assert projected['nodes'][0]['id']=='a'
    assert projected['shared_properties']['dataOrigin']=='ODS scenario'
    assert projected['relationships']==[['n1','p0','n0','edge-1']]
    assert projected['predicates']['p0']['iri']=='urn:verifiedBy'
    assert 'password' not in projected['nodes'][0]['properties']


def test_scratchpad_budgets_nested_json_escaping():
    import json
    original=record(plans=[{'subtasks':['Inspect']}], observations=[
        {'id':'observation-1','tool_id':'read.primary','status':'completed','result':{'text':'"\\'*5000}}])
    pad=goals.scratchpad(original,limit=3000)
    assert len(json.dumps(json.dumps(pad,ensure_ascii=False),ensure_ascii=False).encode())<=3000
    assert original['observations'][0]['result']['text']=='"\\'*5000


def test_alternative_projection_keeps_linked_tests_without_parroting_stored_decision():
    nodes=[{'elementId':key,'properties':{'label':key,'temperature':76}} for key in ('root','option','test','stored-decision')]
    edges=[{'elementId':'edge-option','start':'root','end':'option','properties':{'predicate':'urn:considersAlternative'}},
           {'elementId':'edge-test','start':'option','end':'test','type':'VERIFIED_BY'},
           {'elementId':'edge-decision','start':'stored-decision','end':'root','type':'BASED_ON'}]
    # URI local names in actual RDF properties use slash/hash; use the explicit vocabulary URI.
    edges[0]['properties']['predicate']='https://example.org/eng#considersAlternative'
    result=goals.graph_context_prompt({'root_node_id':'root','nodes':nodes,'relationships':edges,'view':{'truncated':False}},'Compare recorded alternatives')
    assert {node['id'] for node in result['nodes']}=={'root','option','test'}
    assert result['nodes_omitted_from_prompt']==1
    assert len(result['relationships'])==2
    assert result['nodes'][2]['properties']=={} or result['shared_properties']['temperature']=='76'


@pytest.mark.asyncio
async def test_duplicate_read_recovers_to_cited_conclusion_without_another_dispatch():
    seen=[]
    async def propose(available, context):
        seen.append(available)
        step=len(seen)
        if step==1:return action('goal.plan',subtasks=['Read and compare'])
        if step in (2,3):return action('read.primary',ontology_id='selected')
        complete=next(tool for tool in available if tool['id']=='goal.complete')
        assert complete['input_schema']['properties']['evidence_steps']['items']['enum']==['observation-2']
        assert {tool['id'] for tool in available}=={'goal.complete','goal.needs_input'}
        return action('goal.complete',summary='Recorded option B meets the selected criteria.',evidence_steps=['observation-2'])
    dispatch=AsyncMock(return_value={'temperature':76})
    result=await goals.drive(record(),propose=propose,dispatch=dispatch,save=AsyncMock(),tools=TOOLS)
    assert result['status']=='completed'
    assert result['observations'][-1]['error_code']=='duplicate_read'
    assert dispatch.await_count==1


def test_completion_citation_choices_exclude_failed_and_truncated_evidence():
    state=record(observations=[{'id':'ok','status':'completed','result':{'temperature':76}},
        {'id':'failed','status':'failed','result':{'error':'timeout'}},
        {'id':'partial','status':'completed','result':{'truncated':True}}])
    action=goals.completion_action(state)
    assert action['input_schema']['properties']['evidence_steps']['items']['enum']==['ok']
    assert 'enum' not in goals.COMPLETE['input_schema']['properties']['evidence_steps']['items']


@pytest.mark.asyncio
async def test_selected_alternative_comparison_requires_explicit_criteria():
    tool={'id':'graph.business_context','input_schema':{'type':'object','properties':{'ontology_id':{'type':'string'}},'required':['ontology_id'],'additionalProperties':False}}
    state=record(context={'page':'recommendations','decision_analysis':'alternatives'})
    async def propose(available, context):
        if not context['plans']:return action('goal.plan',subtasks=['Compare recorded alternatives'])
        if not context['observations']:return action('graph.business_context',ontology_id='selected')
        assert [item['id'] for item in available]==['goal.complete']
        return action('goal.complete',summary='Values are recorded, but suitability remains subject to review.',evidence_steps=['observation-2'])
    dispatch=AsyncMock(return_value={'nodes':[],'relationships':[],'view':{'truncated':False}})
    result=await goals.drive(state,propose=propose,dispatch=dispatch,save=AsyncMock(),tools=[tool])
    assert result['status']=='needs_input'
    assert dispatch.await_count==1
