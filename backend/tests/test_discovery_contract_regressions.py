import ast
from pathlib import Path

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from backend.depo_platform.service_runtime import create_service_app
from backend.depo_platform.authorization import graph_read_identity
from backend.depo_platform.openapi_contract import contract_errors
from backend.qif.models import QifTaskResponse


def make_app(capabilities=None):
    app = create_service_app(title='Contract test', version='1', dependencies=())
    app.include_router(create_odata_catalog_router(service_name='ContractTest', capabilities=capabilities or [ServiceCapability('A', '/a'), ServiceCapability('B', '/b')]))
    return app


@pytest.mark.parametrize('path,code', [
    ('$filter=Name%20eq%20%27A%27', 'UnsupportedQueryOption'),
    ('$orderby=Name', 'UnsupportedQueryOption'),
    ('$top=-1', 'InvalidQueryOption'),
    ('$top=1001', 'InvalidQueryOption'),
    ('$count=1', 'InvalidQueryOption'),
    ('$skip=0&$skip=1', 'InvalidQueryOption'),
])
def test_invalid_odata_options(path, code):
    response = TestClient(make_app()).get('/odata/ServiceCapabilities?' + path)
    assert response.status_code == 400
    assert response.json()['error']['code'] == code
    assert response.headers['OData-Version'] == '4.0'


def test_zero_paging_count_and_key_lookup():
    client = TestClient(make_app())
    payload = client.get('/odata/ServiceCapabilities?$top=0&$count=true').json()
    assert payload['value'] == [] and payload['@odata.count'] == 2
    entry = client.get('/odata/ServiceCapabilities?$skip=1&$top=1').json()['value'][0]
    response = client.get(f"/odata/ServiceCapabilities('{entry['Id']}')")
    assert response.status_code == 200 and response.json()['Name'] == 'B'
    assert client.get("/odata/ServiceCapabilities('missing')").json()['error']['code'] == 'NotFound'


@pytest.mark.parametrize('module', sorted(Path('backend').glob('*/app.py')))
def test_each_service_declared_catalog_has_unique_keys(module):
    tree = ast.parse(module.read_text(encoding='utf-8-sig'))
    capabilities = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'ServiceCapability':
            args = [ast.literal_eval(arg) for arg in node.args]
            capabilities.append(ServiceCapability(*args))
    if not capabilities:
        pytest.skip('Not a catalog service')
    rows = TestClient(make_app(capabilities)).get('/odata/ServiceCapabilities').json()['value']
    assert len(rows) == len({row['Id'] for row in rows})


def test_nullable_schema_and_security_are_valid_openapi_30():
    app = make_app()
    @app.get('/typed', response_model=QifTaskResponse, dependencies=[Depends(graph_read_identity)])
    def typed():
        pass
    schema = app.openapi()
    validate(schema)
    assert not contract_errors(schema)
    assert schema['components']['schemas']['QifTaskResponse']['properties']['validation']['nullable']
    assert schema['paths']['/typed']['get']['security'] == [{'BearerKey': []}, {'ApiKey': []}]
    # Documentation never changes runtime enforcement.
    assert TestClient(app).get('/typed').status_code == 403


def test_duplicate_capabilities_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        make_app([ServiceCapability('A', '/a'), ServiceCapability('A', '/a')])
