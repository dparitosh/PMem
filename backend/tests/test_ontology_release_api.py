"""Exercise actual release handlers/body schemas with real authorization."""
import ast
from pathlib import Path
import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from backend.depo_platform.authorization import approval_identity, graph_read_identity, service_write_identity
from backend.depo_platform.ontology_maintenance import ontology_writer
from backend.depo_platform.request_bodies import OntologyReleaseBody
from backend.tests.test_ontology_release_lineage import setup, payload


@pytest.fixture
def api(monkeypatch):
    for key in ['DEPO_DATABASE_URL','DATABASE_URL','DEPO_CREDENTIAL_STORAGE','DEPO_REQUIRE_TOKEN_ACTOR']:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('AUTH_MODE','token')
    monkeypatch.setenv('GRAPH_READ_TOKEN','test-reader-key')
    monkeypatch.setenv('ONTOLOGY_APPROVAL_TOKEN','test-approval-key')
    service, catalog = setup()
    scope = dict(router=APIRouter(), releases=service, catalog=catalog, Request=Request,
                 HTTPException=HTTPException, approval_identity=approval_identity,
                 OntologyReleaseBody=OntologyReleaseBody, ontology_writer=ontology_writer)
    tree = ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if getattr(n,'name','') in {'ontology_release_history','declare_ontology_release'}]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<release-routes>','exec'),scope)
    identity_scope = dict(Request=Request,graph_read_identity=graph_read_identity,service_write_identity=service_write_identity)
    identity_tree=ast.parse(Path('backend/ontology_service/modeling_router.py').read_text(encoding='utf-8'))
    identity=next(n for n in identity_tree.body if getattr(n,'name','')=='_modeling_identity')
    exec(compile(ast.Module(body=[identity],type_ignores=[]),'<ontology-auth>','exec'),identity_scope)
    app=FastAPI()
    app.include_router(scope['router'], dependencies=[Depends(identity_scope['_modeling_identity'])])
    return TestClient(app),service


def test_read_requires_access_and_legacy_is_explicit(api):
    client,service=api
    assert client.get('/first/releases').status_code==403
    response=client.get('/first/releases',headers={'Authorization':'Bearer test-reader-key'})
    assert response.status_code==200 and response.json()['release'] is None
    assert not service.store.values


def test_reader_cannot_declare_without_approval(api):
    client,service=api
    response=client.post('/first/releases',headers={'Authorization':'Bearer test-reader-key'},json={**payload(),'approved_by':'reviewer'})
    assert response.status_code==403 and not service.store.values


def test_authorized_declaration_and_strict_contract(api):
    client,service=api
    headers={'Authorization':'Bearer test-approval-key'}
    body={**payload(),'approved_by':'reviewer','approval_token':'test-approval-key'}
    response=client.post('/first/releases',headers=headers,json=body)
    assert response.status_code==200 and response.json()['version']=='1.0.0'
    assert client.post('/first/releases',headers=headers,json=body).json()==response.json()
    assert client.post('/second/releases',headers=headers,json={**body,'version':1}).status_code==422
    assert client.get('/missing/releases',headers={'Authorization':'Bearer test-reader-key'}).status_code==404
    assert '/{ontology_id}/releases' in client.get('/openapi.json').json()['paths']
