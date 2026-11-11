import ast
from pathlib import Path
from unittest.mock import patch
import pytest

from backend.Services.ontology_semantic_runtime import OntologySemanticRuntime

ROOT = Path(__file__).resolve().parents[2]


def test_semantica_validation_runs_without_the_removed_engine(tmp_path, monkeypatch):
    import sys
    from semantica.ontology import OntologyEngine
    monkeypatch.setitem(sys.modules, 'owlready2', None)
    source = tmp_path / 'part.ttl'
    source.write_text('@prefix owl:<http://www.w3.org/2002/07/owl#> . <urn:Part> a owl:Class .')
    original = OntologyEngine.validate
    calls = []
    def validate(self, ontology, **options):
        calls.append(ontology)
        return original(self, ontology, **options)
    with patch.object(OntologyEngine, 'validate', validate):
        result = OntologySemanticRuntime.inspect_ontology(source, 'part')
    assert len(calls) == 1
    assert calls[0]['classes'][0]['iri'] == 'urn:Part'
    assert result['engine'] == 'semantica'
    assert result['structural_validation']['status'] == 'passed'
    assert result['structural_validation']['scope'] == 'structure_only'
    assert result['deductive_reasoner_executed'] is False
    assert result['consistency_verified'] is False


def test_source_imports_and_dependency_profiles_do_not_require_the_removed_engine():
    assert not (ROOT / 'backend/Services/owlready_runtime.py').exists()
    for path in (ROOT / 'backend').rglob('*.py'):
        if 'tests' in path.parts or any(part.startswith(('.dt_venv', '.venv')) for part in path.parts):
            continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            names = [node.module or ''] if isinstance(node, ast.ImportFrom) else [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            assert not any('owlready' in name.lower() for name in names), str(path)
    for path in [ROOT/'backend/requirements.txt', ROOT/'backend/requirements-lock.txt', *(ROOT/'backend/dependency-profiles').glob('*.txt')]:
        assert not any(line.lower().startswith('owlready2') for line in path.read_text().splitlines()), str(path)
    assert 'semantica==0.6.7' in (ROOT/'backend/requirements.txt').read_text()
    for service in ('ontology','graph','schema-sets'):
        assert 'semantica==0.6.7' in (ROOT/f'backend/dependency-profiles/{service}.txt').read_text()


def test_lightweight_conversion_reports_validation_not_executed(tmp_path, monkeypatch):
    import builtins
    original_import = builtins.__import__
    def unavailable(name, *args, **kwargs):
        if name == 'semantica.ontology':
            raise ModuleNotFoundError("No module named 'semantica'", name='semantica')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', unavailable)
    source = tmp_path / 'part.ttl'
    source.write_text('@prefix owl:<http://www.w3.org/2002/07/owl#> . <urn:Part> a owl:Class .')
    result = OntologySemanticRuntime.inspect_ontology(source)
    assert result['status'] == 'success'
    assert result['engine'] == 'rdflib'
    assert result['summary']['classes'] == 1
    assert result['structural_validation']['status'] == 'not_executed'
    assert result['consistency_verified'] is False


def test_taxonomy_preserves_distinct_iris_and_excludes_anonymous_restriction_nodes(tmp_path):
    source = tmp_path / 'parts.ttl'
    source.write_text('''
        @prefix owl:<http://www.w3.org/2002/07/owl#> .
        @prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> .
        <https://one.example/Part> a owl:Class ; rdfs:label "Part" ;
            rdfs:subClassOf [ a owl:Restriction ; owl:onProperty <urn:hasPart> ;
                              owl:someValuesFrom <https://two.example/Part> ] .
        <https://two.example/Part> a owl:Class ; rdfs:label "Part" .
    ''')
    first = OntologySemanticRuntime.extract_taxonomy(source, 'product')
    second = OntologySemanticRuntime.extract_taxonomy(source, 'product')
    assert {row['term_id'] for row in first['nodes']} == {
        'https://one.example/Part', 'https://two.example/Part'}
    assert first['nodes'] == second['nodes']
    assert first['edges'] == second['edges'] == []
    assert first['summary']['classes'] == 2


@pytest.mark.parametrize('suffix,content', [
    ('.nt', '<urn:Part> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2002/07/owl#Class> .'),
    ('.n3', '@prefix owl:<http://www.w3.org/2002/07/owl#> . <urn:Part> a owl:Class .'),
])
def test_retained_rdf_serializations_remain_browsable(tmp_path, suffix, content):
    source = tmp_path / ('part' + suffix)
    source.write_text(content)
    result = OntologySemanticRuntime.inspect_ontology(source)
    assert result['status'] == 'success'
    assert result['summary']['classes'] == 1


def test_asserted_class_references_are_available_to_bridge_target_resolution(tmp_path):
    source = tmp_path / 'parts.ttl'
    source.write_text('''@prefix owl:<http://www.w3.org/2002/07/owl#> .
        @prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> .
        <urn:Motor> rdfs:subClassOf <urn:Part> .
        <urn:hasOwner> a owl:ObjectProperty ; rdfs:domain <urn:Part> ; rdfs:range <urn:Organization> .''')
    result = OntologySemanticRuntime.inspect_ontology(source)
    assert {row['iri'] for row in result['classes']} == {'urn:Motor', 'urn:Part', 'urn:Organization'}


def test_extractor_keeps_business_definitions(tmp_path):
    from backend.Services.ontology_extractor import OWLRDFExtractor
    source = tmp_path / 'parts.ttl'
    source.write_text('''@prefix owl:<http://www.w3.org/2002/07/owl#> .
        @prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> .
        <urn:Part> a owl:Class ; rdfs:label "Part" ; rdfs:comment "An engineering item." .''')
    result = OWLRDFExtractor(str(source)).extract()
    assert result['entities']['Part']['description'] == 'An engineering item.'


def test_broken_installed_semantica_is_not_reported_as_optional_absence(tmp_path, monkeypatch):
    import builtins
    original_import = builtins.__import__
    def broken(name, *args, **kwargs):
        if name == 'semantica.ontology':
            raise ModuleNotFoundError('Broken package', name='semantica.ontology.internal')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', broken)
    source = tmp_path / 'part.ttl'
    source.write_text('@prefix owl:<http://www.w3.org/2002/07/owl#> . <urn:Part> a owl:Class .')
    with pytest.raises(ModuleNotFoundError, match='Broken package'):
        OntologySemanticRuntime.inspect_ontology(source)


def test_malformed_ntriples_returns_a_structured_failure(tmp_path):
    source = tmp_path / 'broken.nt'
    source.write_text('not RDF')
    result = OntologySemanticRuntime.inspect_ontology(source)
    assert result['status'] == 'unsupported'
    assert result['summary']['classes'] == 0


def test_legacy_taxonomy_rejects_remote_context_before_parser_io(tmp_path, monkeypatch):
    from backend.ontology_service.domain.taxonomy import OntologyTaxonomyService
    source = tmp_path / 'remote.jsonld'
    source.write_text('{"@context":"https://example.invalid/context","@id":"urn:Part"}')
    with patch('backend.ontology_service.domain.taxonomy.Graph.parse') as parse:
        result = OntologyTaxonomyService._parse_rdf({'prefix': 'part'}, source)
    parse.assert_not_called()
    assert result['source'] == 'rdf_parse_error'


def test_extractor_does_not_bypass_artifact_size_rejection(tmp_path, monkeypatch):
    from backend.Services.ontology_extractor import OWLRDFExtractor
    monkeypatch.setattr('backend.depo_platform.upload_limits.ontology_upload_limit', lambda: 5)
    source = tmp_path / 'parts.ttl'
    source.write_text('@prefix owl:<http://www.w3.org/2002/07/owl#> . <urn:Part> a owl:Class .')
    with pytest.raises(ValueError, match='Ontology inspection failed'):
        OWLRDFExtractor(str(source)).extract()
