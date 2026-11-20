import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from backend.agentic_service.recommendation_goals import selection, validate_read, completion_evidence, bound_inputs, TOOLS
from backend.agentic_service import goal_runner as goals
from backend.tests.test_read_goal_runner import record, action

CONTEXT={'recommendation_service':'similar-parts','recommendation_object':'Motor','recommendation_top_n':5,'ontology_id':'selected'}
INPUTS={'part_name':'Motor','top_n':5,'scope':{'ontology_id':'selected'}}
TOOL={'id':TOOLS['similar-parts'],'mutates':False,'input_schema':{'type':'object'}}

def observation(policy='passed'):
 return {'id':'observation-2','status':'completed','tool_id':TOOL['id'],'inputs':copy.deepcopy(INPUTS),'result':{'decision_policy':{'status':policy}}}

@pytest.mark.parametrize('changed',[{'recommendation_service':[]},{'recommendation_object':''},{'recommendation_top_n':True},{'recommendation_top_n':51}])
def test_invalid_selection_is_rejected(changed):
 with pytest.raises(ValueError):selection({**CONTEXT,**changed})

@pytest.mark.parametrize('changed',[{'part_name':'Other'},{'top_n':10},{'scope':{}},{'node_id':'other'}])
def test_model_cannot_change_selected_object_limit_or_scope(changed):
 with pytest.raises(ValueError):validate_read(CONTEXT,TOOL['id'],{**INPUTS,**changed})

def test_another_analysis_cannot_substitute_for_the_selection():
 with pytest.raises(ValueError):validate_read(CONTEXT,TOOLS['change-impact'],{'change_name':'Motor'})

def test_citation_requires_selected_recommendation_and_policy_evidence():
 for candidate in [[],[{**observation(),'tool_id':'graph.analytics'}],[{**observation(),'result':{}}],[{**observation(),'result':{'truncated':True}}]]:
  with pytest.raises(ValueError):completion_evidence(CONTEXT,candidate,['observation-2'])
 for state in ['passed','blocked','not_configured','unavailable']:
  assert completion_evidence(CONTEXT,[observation(state)],['observation-2'])['decision_policy_status']==state

@pytest.mark.asyncio
async def test_existing_controller_retains_policy_result_and_cites_observation():
 decisions=[action('goal.plan',subtasks=['Read selected recommendation and review Semantica policy']),action(TOOL['id'],**INPUTS),action('goal.complete',summary='Policy holds this graph-derived advice.',evidence_steps=['observation-2'])]
 result=await goals.drive(record(context=CONTEXT),propose=AsyncMock(side_effect=decisions),dispatch=AsyncMock(return_value={'decision_policy':{'status':'blocked'}}),save=AsyncMock(),tools=[TOOL])
 assert result['status']=='completed'
 assert result['result']['recommendation_observation_id']=='observation-2'
 assert result['result']['decision_policy_status']=='blocked'
 assert result['result']['advisory_only'] is True

def test_existing_graph_analyst_has_only_read_recommendation_bindings():
 catalog=json.loads((Path(__file__).resolve().parents[1]/'agentic_service/catalog.json').read_text())
 agent=next(a for a in catalog['agents'] if a['id']=='graph-analyst')
 for service,identifier in TOOLS.items():
  tool=next(t for t in catalog['tools'] if t['id']==identifier)
  assert identifier in agent['tools'] and tool['mutates'] is False
  assert tool['service']=='graph' and tool['path']=='/recommendations/'+service


def test_graph_tools_resolve_under_the_canonical_api_base():
 import ast
 from backend.depo_platform.request_bodies import ContextBody
 from backend.agentic_service.proposal_contracts import input_schema
 from pydantic import TypeAdapter
 schema=TypeAdapter(ContextBody).json_schema()
 for service,identifier in TOOLS.items():
  document={'paths':{'/api/v1/recommendations/'+service:{'post':{'requestBody':{'content':{'application/json':{'schema':schema}}}}}},'$defs':schema.get('$defs',{})}
  resolved=input_schema(document,{'method':'POST','path':'/recommendations/'+service,'id':identifier})
  assert 'scope' in resolved['properties']
 tree=ast.parse((Path(__file__).resolve().parents[1]/'graph_service/context_router.py').read_text())
 paths={decorator.args[0].value for node in tree.body for decorator in getattr(node,'decorator_list',[]) if isinstance(decorator,ast.Call) and getattr(decorator.func,'attr','')=='post'}
 assert all('/api/v1/recommendations/'+service in paths for service in TOOLS)


def test_tools_advertise_the_controller_evidence_contract():
 from backend.agentic_service import router
 response=router.tools()
 assert response['read_goal_capabilities']['recommendation_evidence']==1
 assert set(TOOLS.values()).issubset({tool['id'] for tool in response['tools']})


def test_co_recommendation_does_not_present_zero_counts_as_impact():
 context={'recommendation_service':'change-impact','recommendation_object':'Shaft','node_id':'selected','ontology_id':'source'}
 evidence={'id':'impact','status':'completed','tool_id':TOOLS['change-impact'], 'inputs':bound_inputs(context),
  'result':{'decision_policy':{'status':'not_configured'},'assembly_impact':[], 'process_impacts':[], 'impacted_requirements':[], 'impacted_parts':[]}}
 summary=completion_evidence(context,[evidence],['impact'])['business_summary']
 assert 'hold release' in summary
 assert 'CO scope' in summary
 assert 'records: 0' not in summary
 evidence['result']['assembly_impact']=[{'name':'Motor assembly'}]
 summary=completion_evidence(context,[evidence],['impact'])['business_summary']
 assert 'include Motor assembly' in summary
 assert 'before release' in summary


def test_large_path_evidence_is_compacted_only_for_the_model():
 from backend.agentic_service.recommendation_goals import prompt_evidence
 item=observation()
 item['result']['similar_parts']=[{'node_id':'part-1','name':'Comparable bearing','similarity_score':90,'path':[{'detail':'x'*100000}]}]
 original=copy.deepcopy(item)
 compact=prompt_evidence(CONTEXT,item)
 assert len(json.dumps(compact)) < 3000
 assert compact['similar_parts'][0]['name']=='Comparable bearing'
 assert compact['full_evidence_retained'] is True
 assert item==original


@pytest.mark.asyncio
async def test_large_typed_recommendation_remains_complete_in_durable_state():
 result={'decision_policy':{'status':'passed'},'similar_parts':[{'node_id':'part','name':'Bearing candidate','path':[{'detail':'x'*40000}]}]}
 decisions=[action('goal.plan',subtasks=['Read evidence']),action(TOOL['id'],**INPUTS),action('goal.complete',summary='Review candidate',evidence_steps=['observation-2'])]
 saved=await goals.drive(record(context=CONTEXT),propose=AsyncMock(side_effect=decisions),dispatch=AsyncMock(return_value=result),save=AsyncMock(),tools=[TOOL])
 assert saved['status']=='completed'
 assert saved['observations'][0]['result']==result
 assert len(json.dumps(goals.scratchpad(saved))) < 10000


def test_conflicting_candidates_are_not_recommended_as_alternatives():
 item=observation()
 item['result']['similar_parts']=[{'name':'Bearing candidate','conflicts':[]},{'name':'Wrong shaft','conflicts':['material','dimensions'],'compatibility':'conflicting_evidence'}]
 summary=completion_evidence(CONTEXT,[item],['observation-2'])['business_summary']
 assert 'Bearing candidate' in summary
 assert 'Wrong shaft' not in summary
