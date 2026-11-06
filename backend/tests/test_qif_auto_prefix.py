from pathlib import Path
import pytest
from fastapi import HTTPException
from backend.qif.router import _source_prefix


def schema(tmp_path, name, namespace):
    path = tmp_path / name
    path.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="' + namespace + '"/>')
    return path


def test_qif_prefix_comes_from_namespace_not_filename_or_profile(tmp_path):
    source = schema(tmp_path, 'qif.xsd', 'urn:customer:product')
    assert _source_prefix([source], '') == 'product'
    assert _source_prefix([source], 'chosen') == 'chosen'


def test_shared_namespace_and_missing_namespace(tmp_path):
    a = schema(tmp_path, 'a.xsd', 'https://example.org/Model#')
    b = schema(tmp_path, 'b.xsd', 'https://example.org/Model#')
    assert _source_prefix([a, b], '') == 'model'
    assert _source_prefix([schema(tmp_path, 'none.xsd', '')], '') == 'ontology'


def test_multiple_namespaces_require_explicit_choice(tmp_path):
    paths = [schema(tmp_path, 'a.xsd', 'urn:a'), schema(tmp_path, 'b.xsd', 'urn:b')]
    with pytest.raises(HTTPException) as caught:
        _source_prefix(paths, '')
    assert caught.value.status_code == 422
    assert _source_prefix(paths, 'combined') == 'combined'


def test_upload_contract_does_not_require_prefix():
    from backend.qif.app import app
    contract = app.openapi()
    for route in ('/api/v1/qif/tasks/upload', '/api/v1/qif/schema-sets/upload'):
        body = contract['paths'][route]['post']['requestBody']['content']['multipart/form-data']['schema']
        schema_name = body['$ref'].rsplit('/', 1)[-1]
        assert 'prefix' not in contract['components']['schemas'][schema_name].get('required', [])
