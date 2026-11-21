"""Inference advisor uses the real read endpoints and retains source scope."""
import copy
from pathlib import Path

import pytest
from fastapi import FastAPI
from backend.agentic_service.catalog_loader import load_catalog
from backend.agentic_service.catalog_contract import validate_catalog
from backend.agentic_service.goal_runner import read_tools, validate_action
from backend.agentic_service.input_contracts import validate
from backend.agentic_service.proposal_contracts import input_schema
from backend.ingestion_service.api.ontology_browser import router
from backend.ontology_service.router import router as ontology_router


def inference_tools():
    catalog = validate_catalog(load_catalog())
    agent = next(item for item in catalog['agents'] if item['id'] == 'ontology-inference')
    tools = read_tools(agent, catalog['tools'], lambda payload: {'requires_approval': False})
    app = FastAPI(); app.include_router(router, prefix='/api/v1')
    ontology_app = FastAPI(); ontology_app.include_router(ontology_router)
    documents = {'ingestion': app.openapi(), 'ontology': ontology_app.openapi()}
    return agent, [{**tool, 'input_schema': input_schema(documents[tool['service']], tool)} for tool in tools]


def test_registered_inference_tools_match_live_openapi_and_are_read_only():
    agent, tools = inference_tools()
    assert not agent['approval_required']
    assert {tool['id'] for tool in tools} == {'ontology.inference.preview', 'ontology.reasoning.inspect',
        'ontology.foundation.inspect', 'ontology.semantic.evidence', 'ontology.consistency.check', 'ontology.inspection_rules.assess'}
    preview = next(tool for tool in tools if tool['id'] == 'ontology.inference.preview')
    values = {'ontology_id':'selected', 'rules':{'transitive_subclass':True}, 'limit':25}
    validate(values, preview['input_schema'], preview['input_schema'])
    for bad in ({**values, 'limit':1001}, {**values, 'limit':True}):
        with pytest.raises(ValueError):
            validate(bad, preview['input_schema'], preview['input_schema'])
    record = {'scope':{'ontology_id':'selected'}, 'plans':[{'revision':1}], 'observations':[]}
    assert validate_action(record, {'tool_id':preview['id'], 'inputs':values}, tools)[1] == values
    with pytest.raises(ValueError, match='scope|outside'):
        validate_action(record, {'tool_id':preview['id'], 'inputs':{**values, 'ontology_id':'another'}}, tools)


def test_nullable_preview_body_becomes_object_tool_contract_without_losing_fields():
    _,tools=inference_tools()
    schema=next(t['input_schema'] for t in tools if t['id']=='ontology.inference.preview')
    assert schema['type']=='object' and 'anyOf' not in schema
    assert {'rules','limit','ontology_id'} <= set(schema['properties'])
    assert 'ontology_id' in schema['required']
    with pytest.raises(ValueError):
        validate({'ontology_id':'selected','limit':0},schema,schema)


def test_retained_rule_observation_cannot_change_selected_ontology():
    from backend.agentic_service.goal_runner import verify_read_identity
    with pytest.raises(ValueError,match='identity'):
        verify_read_identity('ontology.inspection_rules.assess',{'ontology_id':'selected'},{'ontology_id':'other'})


def test_openapi30_optional_body_wrapper_preserves_original_constraints():
    document={'paths':{'/api/v1/preview':{'post':{'requestBody':{'content':{'application/json':{'schema':{
        'type':'object','nullable':True,'allOf':[{'type':'object','additionalProperties':False,
        'properties':{'limit':{'type':'integer','minimum':25,'maximum':1000}}}]}}}},
        'parameters':[{'in':'path','name':'ontology_id','required':True,'schema':{'type':'string'}}]}}}}
    original=copy.deepcopy(document)
    schema=input_schema(document,{'id':'preview','path':'/preview','method':'POST'})
    assert schema['type']=='object' and 'allOf' not in schema
    assert document==original
    validate({'ontology_id':'selected','limit':25},schema,schema)
    with pytest.raises(ValueError):validate({'ontology_id':'selected','limit':0},schema,schema)
    with pytest.raises(ValueError):validate({'ontology_id':'selected','invented':True},schema,schema)
