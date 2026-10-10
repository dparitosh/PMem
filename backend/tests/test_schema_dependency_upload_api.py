"""Test the multipart boundary independently of optional ontology runtimes."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
import httpx
from backend.ingestion_service.engineering_workflow import EngineeringDependencyFailure
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool


def client_and_calls(engineering=False, result=None, failure=None):
    tree = ast.parse(Path('backend/ingestion_service/router.py').read_text(encoding='utf-8'))
    handler = 'run_engineering_workflow' if engineering else 'inspect_engineering_schema'
    nodes = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name in {'_read_bounded_upload',handler}]
    for node in nodes: node.decorator_list = []
    calls = []
    def convert(**kwargs):
        calls.append(kwargs)
        return {'status':'ok','dependencies': list(kwargs.get('schema_files',{}))}
    async def run(**kwargs):
        converted = convert(**kwargs)
        if failure is not None:
            raise failure
        return result if result is not None else converted
    scope = {'UploadFile':UploadFile,'File':File,'Form':Form,'HTTPException':HTTPException,
        'MAX_UPLOAD_BYTES':25*1024*1024,'json':json,'Path':Path,'run_in_threadpool':run_in_threadpool,
        'converter':SimpleNamespace(convert=convert), 'engineering_workflow':SimpleNamespace(run=run),
        'Request':Request, 'httpx':httpx, 'EngineeringDependencyFailure':EngineeringDependencyFailure}
    exec(compile(ast.Module(body=nodes,type_ignores=[]), '<actual multipart handler>', 'exec'),scope)
    app=FastAPI(); app.post('/inspect')(scope[handler])
    return TestClient(app), calls


def test_multipart_dependency_names_match_selected_order():
    client,calls=client_and_calls()
    response=client.post('/inspect',files=[('file',('main.xsd',b'root')),('dependencies',('part.xsd',b'part'))],
        data={'dependency_paths':'["types/part.xsd"]'})
    assert response.status_code == 200
    assert calls[0]['schema_files'] == {'types/part.xsd':b'part'}


def test_mismatched_and_duplicate_dependencies_fail_before_conversion():
    client,calls=client_and_calls()
    files=[('file',('main.xsd',b'root')),('dependencies',('one.xsd',b'one')),('dependencies',('two.xsd',b'two'))]
    for paths in ('[]','["one.xsd","one.xsd"]','{}'):
        assert client.post('/inspect',files=files,data={'dependency_paths':paths}).status_code == 422
    assert not calls


def test_engineering_workflow_receives_dependency_bundle():
    client, calls = client_and_calls(engineering=True)
    response = client.post('/inspect', files=[('file', ('main.xsd', b'root')),
        ('dependencies', ('part.xsd', b'part'))], data={'dependency_paths':'["types/part.xsd"]'})
    assert response.status_code == 200
    assert calls[0]['schema_files'] == {'types/part.xsd':b'part'}


def test_engineering_workflow_rejects_bad_bundle_before_registration():
    client, calls = client_and_calls(engineering=True)
    files=[('file', ('main.xsd', b'root')), ('dependencies', ('part.xsd', b'part'))]
    for paths in ('[]', '{}', '["part.xsd", "part.xsd"]'):
        assert client.post('/inspect', files=files, data={'dependency_paths':paths}).status_code == 422
    assert not calls


def test_compact_response_retains_registration_without_full_conversion():
    result = {'status': 'registered', 'ontology_registration': {'ontology_id': 'source'},
              'conversion': {'format': 'xsd', 'statistics': {'classes': 12},
                             'artifacts': {'ttl': 'retained.ttl'}, 'ttl': 'large generated content'}}
    client, _ = client_and_calls(engineering=True, result=result)
    response = client.post('/inspect', files={'file': ('main.xsd', b'root')},
                           data={'include_conversion': 'false'})
    assert response.status_code == 200
    body = response.json()
    assert body['ontology_registration']['ontology_id'] == 'source'
    assert body['conversion_summary']['statistics']['classes'] == 12
    assert 'conversion' not in body
    assert 'large generated content' not in response.text


def test_dependency_failure_returns_safe_stage_diagnostics():
    client, _ = client_and_calls(engineering=True,
        failure=EngineeringDependencyFailure('quality_gate', 'upstream_timeout'))
    response = client.post('/inspect', files={'file': ('main.xsd', b'root')})
    assert response.status_code == 503
    detail = response.json()['detail']
    assert detail['code'] == 'engineering_dependency_failure'
    assert detail['stage'] == 'quality_gate'
    assert detail['failure_kind'] == 'upstream_timeout'
