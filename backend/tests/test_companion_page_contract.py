import re
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.agentic_service.router import companion_validate

def test_all_canonical_navigation_pages_pass_the_real_chat_validation_endpoint():
    source=(Path(__file__).resolve().parents[2]/'frontend/src/app/navigation.js').read_text(encoding='utf-8')
    pages=re.findall(r"id: '([^']+)'",source)
    assert 'recommendations' in pages and 'change-control' in pages
    app=FastAPI();app.post('/chat/validate')(companion_validate);client=TestClient(app)
    for page in pages:
        response=client.post('/chat/validate',json={'message':'Review the selected engineering evidence','graph_context':{'page':page,'ontology':'parts','node_id':'part:1'}})
        assert response.status_code==200,(page,response.text)
    assert client.post('/chat/validate',json={'message':'Review evidence','graph_context':{'page':'invented-page'}}).status_code==422
