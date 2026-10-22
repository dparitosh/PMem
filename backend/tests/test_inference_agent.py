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


def inference_tools():
    catalog = validate_catalog(load_catalog())
    agent = next(item for item in catalog['agents'] if item['id'] == 'ontology-inference')
    tools = read_tools(agent, catalog['tools'], lambda payload: {'requires_approval': False})
    app = FastAPI(); app.include_router(router, prefix='/api/v1')
    return agent, [{**tool, 'input_schema': input_schema(app.openapi(), tool)} for tool in tools]


def test_registered_inference_tools_match_live_openapi_and_are_read_only():
    agent, tools = inference_tools()
    assert not agent['approval_required']
    assert {tool['id'] for tool in tools} == {'ontology.inference.preview', 'ontology.reasoning.inspect'}
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
