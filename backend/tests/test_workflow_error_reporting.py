import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from backend.agentic_service.workflow_errors import workflow_error


def test_merge_missing_artifact_is_actionable_without_leaking_path():
    response = httpx.Response(422, json={'detail': 'Ontology file is missing: secret-source'}, request=httpx.Request('POST', 'http://ontology/merges/preview'))
    cause = httpx.HTTPStatusError('secret', request=response.request, response=response)
    error = HTTPException(422, 'rejected')
    error.__cause__ = cause
    result = workflow_error(error, 'ontology.merge.preview')
    assert result['http_status'] == 422
    assert result['error_code'] == 'merge_source_missing'
    assert 'secret' not in str(result)


def test_unknown_body_and_exception_details_are_not_retained():
    error = HTTPException(403, 'api-key=secret')
    assert workflow_error(error, 'ontology.merge.preview')['error_code'] == 'scope_rejected'
    assert 'secret' not in str(workflow_error(error, 'ontology.merge.preview'))
    assert 'secret' not in str(workflow_error(RuntimeError('secret'), 'ontology.merge.preview'))


def test_converted_artifact_remains_usable_without_original_upload(tmp_path):
    tree = ast.parse(Path('backend/ontology_service/domain/reasoning.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OntologyReasoningService')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'semantic_context')
    method.decorator_list = []
    namespace = {'Path': Path, 'Dict': dict, 'Any': object, '__package__': 'backend.ontology_service.domain'}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<resolver>', 'exec'), namespace)
    artifact = tmp_path / 'converted.ttl'
    artifact.write_text('<urn:a> <urn:b> <urn:c> .')
    resolver = SimpleNamespace(_resolve_metadata=lambda _: {'ontology_id': 'a', 'file_path': str(tmp_path / 'missing.xsd'), 'owl_file_path': str(artifact)})
    with patch.dict('sys.modules', {'backend.ontology_service.domain.taxonomy': SimpleNamespace(OntologyTaxonomyService=resolver)}):
        assert namespace['semantic_context'](None, 'a')['file_path'] == artifact


def test_taxonomy_uses_retained_rdf_without_original_upload(tmp_path):
    tree = ast.parse(Path('backend/ontology_service/domain/taxonomy.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OntologyTaxonomyService')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_semantic_context')
    method.decorator_list = []
    artifact = tmp_path / 'converted.ttl'
    artifact.write_text('<urn:a> <urn:b> <urn:c> .')
    resolver = SimpleNamespace(_resolve_metadata=lambda _: {'ontology_id': 'a', 'file_path': str(tmp_path / 'missing.xsd'), 'owl_file_path': str(artifact)})
    namespace = {'Path': Path, 'Dict': dict, 'Any': object, 'OntologyTaxonomyService': resolver}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<taxonomy>', 'exec'), namespace)
    context = namespace['_semantic_context']('a')
    assert context['file_path'] == artifact
    assert context['source_file_path'] == artifact
