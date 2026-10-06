"""Test the multipart boundary independently of optional ontology runtimes."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool


def client_and_calls():
    tree = ast.parse(Path('backend/ingestion_service/router.py').read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name in {'_read_bounded_upload','inspect_engineering_schema'}]
    for node in nodes: node.decorator_list = []
    calls = []
    def convert(**kwargs):
        calls.append(kwargs)
        return {'status':'ok','dependencies': list(kwargs.get('schema_files',{}))}
    scope = {'UploadFile':UploadFile,'File':File,'Form':Form,'HTTPException':HTTPException,
        'MAX_UPLOAD_BYTES':25*1024*1024,'json':json,'Path':Path,'run_in_threadpool':run_in_threadpool,
        'converter':SimpleNamespace(convert=convert)}
    exec(compile(ast.Module(body=nodes,type_ignores=[]), '<actual multipart handler>', 'exec'),scope)
    app=FastAPI(); app.post('/inspect')(scope['inspect_engineering_schema'])
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
