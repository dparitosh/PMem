import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rdflib import Graph, URIRef, Literal
from rdflib.compare import isomorphic
from rdflib.namespace import RDF, RDFS, OWL, DCTERMS

from backend.oslc_service.representation import represent, rdf_graph
from backend.oslc_service.ontology_shapes import catalog_shape
from backend.ontology_service.catalog import OntologyCatalog
from backend.Services.ontology_upload_manager import OntologyUploadManager
from backend.Services.ontology_semantic_runtime import OntologySemanticRuntime


def test_oslc_shape_blocks_remote_jsonld_context_before_parser(monkeypatch):
    monkeypatch.setattr(OntologyCatalog, 'read_artifact', lambda *_: (
        {'original_filename': 'unsafe.jsonld'}, b'{"@context":"https://example.invalid/context","@id":"urn:Part"}'))
    with patch('backend.oslc_service.ontology_shapes.Graph.parse') as parse:
        with pytest.raises(ValueError):
            catalog_shape('part', 'https://gateway.example')
        parse.assert_not_called()


def test_namespace_discovery_blocks_remote_jsonld_context_before_parser():
    with patch('rdflib.Graph.parse') as parse:
        assert OntologyUploadManager._derive_ontology_namespace(
            b'{"@context":"https://example.invalid/context","@id":"urn:Part"}', 'unsafe.jsonld', 'ontology') == ''
        parse.assert_not_called()


def test_legacy_ontology_import_parses_jsonld_without_losing_unicode_or_types():
    content = json.dumps({'@context': {'owl':str(OWL), 'rdfs':str(RDFS)},
                          '@id':'urn:Part', '@type':'owl:Class', 'rdfs:label':'部品'}).encode()
    graph = OntologyUploadManager._parse_rdf_content(content, 'parts.jsonld')
    assert (URIRef('urn:Part'), RDF.type, OWL.Class) in graph
    assert (URIRef('urn:Part'), RDFS.label, Literal('部品')) in graph


def test_legacy_ontology_import_rejects_remote_context_before_parser():
    with patch('rdflib.Graph.parse') as parse:
        with pytest.raises(ValueError):
            OntologyUploadManager._parse_rdf_content(
                b'{"@context":"https://example.invalid/context","@id":"urn:Part"}', 'unsafe.jsonld')
        parse.assert_not_called()


def test_oslc_jsonld_preserves_canonical_resource_type_and_description():
    payload = {'uri': 'urn:shape', 'type': 'oslc:ResourceShape',
               'description': 'Engineering parts', 'resourceTypeUri': 'urn:Part'}
    response = represent(payload, SimpleNamespace(headers={'accept': 'application/ld+json'}))
    graph = Graph().parse(data=response.body, format='json-ld')
    assert (URIRef('urn:shape'), DCTERMS.description, Literal('Engineering parts')) in graph
    assert (URIRef('urn:shape'), URIRef('http://open-services.net/ns/core#resourceType'), URIRef('urn:Part')) in graph


def test_jsonld_response_schema_accepts_actual_serialized_array():
    from backend.oslc_service.media import REPRESENTATION_RESPONSES
    schema = REPRESENTATION_RESPONSES[200]['content']['application/ld+json']['schema']
    assert {item['type'] for item in schema['oneOf']} == {'array', 'object'}


def test_oslc_shape_includes_rdfs_class_declarations(monkeypatch):
    monkeypatch.setattr(OntologyCatalog, 'read_artifact', lambda *_: (
        {'original_filename': 'part.jsonld'}, json.dumps({
            '@context': {'rdfs': str(RDFS)}, '@id': 'urn:Part', '@type': 'rdfs:Class'}).encode()))
    assert catalog_shape('part', 'https://gateway.example')['describes'] == ['urn:Part']


def test_jsonld_inline_context_semantics_and_rdf_round_trip(tmp_path):
    source = tmp_path / 'parts.jsonld'
    source.write_text(json.dumps({'@context': {'owl': str(OWL), 'rdfs': str(RDFS),
        'label': {'@id': 'rdfs:label', '@language': 'en'}}, '@graph': [
        {'@id': 'urn:Part', '@type': 'owl:Class', 'label': 'Part'},
        {'@id': 'urn:hasPart', '@type': 'owl:ObjectProperty',
         'rdfs:domain': {'@id': 'urn:Part'}, 'rdfs:range': {'@id': 'urn:Part'}}]}))
    result = OntologySemanticRuntime.inspect_ontology(source)
    assert result['classes'][0]['label'] == 'Part'
    assert result['object_properties'][0]['domain'][0]['iri'] == 'urn:Part'
    original = Graph().parse(data=source.read_bytes(), format='json-ld')
    assert isomorphic(original, Graph().parse(data=original.serialize(format='turtle'), format='turtle'))
    assert isomorphic(original, Graph().parse(data=original.serialize(format='json-ld'), format='json-ld'))


@pytest.mark.parametrize('media,syntax', [('text/turtle','turtle'), ('application/rdf+xml','xml'), ('application/ld+json','json-ld')])
def test_oslc_representation_roundtrip_preserves_shapes_links_and_typed_values(media, syntax):
    payload = {'uri': 'urn:query', 'type': 'oslc:QueryResult', 'members': [
        {'uri': 'urn:part', 'type': 'oslc_am:Resource', 'title': 'Motor – 部品',
         'domainProperties': {'oslc_rm:uses': ['urn:req'], 'oslc_cm:status': 'approved'},
         'enabled': True, 'quantity': 2}], 'nextPage': 'https://gateway.example/oslc/query/resources?page=2'}
    response = represent(payload, SimpleNamespace(headers={'accept': media}))
    assert response.headers['vary'] == 'Accept'
    assert response.headers['oslc-core-version'] == '2.0'
    assert isomorphic(rdf_graph(payload), Graph().parse(data=response.body, format=syntax))


@pytest.mark.parametrize('context', [
    ['https://example.invalid/context'],
    {'nested': {'@id': 'urn:nested', '@context': 'https://example.invalid/context'}},
    {'@import': 'https://example.invalid/context'},
])
def test_jsonld_context_guards_cover_nested_imports_and_context_arrays(context):
    content = json.dumps({'@context': context, '@id': 'urn:Part'}).encode()
    with patch('backend.ontology_service.catalog.Graph.parse') as parse:
        with pytest.raises(ValueError):
            OntologyCatalog._parse_ontology(content, 'unsafe.jsonld')
        parse.assert_not_called()


def test_builtin_oslc_shape_domain_is_a_namespace_iri():
    response = represent({'uri':'urn:shape', 'type':'oslc:ResourceShape', 'domain':'oslc_rm'},
                         SimpleNamespace(headers={'accept':'application/ld+json'}))
    graph = Graph().parse(data=response.body, format='json-ld')
    assert (URIRef('urn:shape'), URIRef('http://open-services.net/ns/core#domain'),
            URIRef('http://open-services.net/ns/rm#')) in graph


def test_http_discovery_shapes_and_failure_contracts(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routes.oslc_routes import router, graph_read_identity
    from backend.Services.oslc_service import OSLCService
    monkeypatch.setattr(OSLCService, 'is_enabled', lambda: True)
    monkeypatch.setattr(OSLCService, '_ontology_domains', lambda: [])
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[graph_read_identity] = lambda: 'fixture-reader'
    client = TestClient(app)
    response = client.get('/oslc/providers/' + OSLCService.config().provider_id,
                          headers={'Accept':'application/ld+json'})
    assert response.status_code == 200
    graph = Graph().parse(data=response.content, format='json-ld')
    resource_types = set(graph.objects(None, URIRef('http://open-services.net/ns/core#resourceType')))
    assert URIRef(OSLCService.AM_TYPE_URI) in resource_types
    assert URIRef(OSLCService.RM_REQUIREMENT_URI) in resource_types
    shape = client.get('/oslc/shapes/requirements', headers={'Accept':'application/ld+json'})
    assert shape.status_code == 200
    assert (None, RDF.type, URIRef('http://open-services.net/ns/core#ResourceShape')) in Graph().parse(data=shape.content, format='json-ld')
    assert client.get('/oslc/providers/missing').status_code == 404
    assert client.get('/oslc/shapes/requirements', headers={'Accept':'image/png'}).status_code == 406
    monkeypatch.setattr(OSLCService, 'query_resources', lambda *_: (_ for _ in ()).throw(RuntimeError('dependency failed')))
    assert client.get('/oslc/query/requirements').status_code == 503
    monkeypatch.setattr(OSLCService, 'is_enabled', lambda: False)
    assert client.get('/oslc/shapes/requirements').status_code == 404


@pytest.mark.parametrize('format,syntax', [('ttl','turtle'), ('rdf','xml'), ('jsonld','json-ld')])
def test_http_export_from_jsonld_preserves_language_types_and_relationships(tmp_path, monkeypatch, format, syntax):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.ingestion_service.api.ontology_browser import router, graph_read_identity, OntologyReasoningService
    source = tmp_path/'part.jsonld'
    source.write_text(json.dumps({'@context': {'owl':str(OWL), 'rdfs':str(RDFS)},
        '@id':'urn:Part', '@type':'owl:Class', 'rdfs:label':{'@value':'部品', '@language':'ja'},
        'rdfs:subClassOf':{'@id':'urn:Product'}}))
    monkeypatch.setattr(OntologyReasoningService, 'semantic_context', lambda _: {'file_path':source})
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[graph_read_identity] = lambda: 'fixture-reader'
    response = TestClient(app).get('/ontology/part/export', params={'format':format})
    assert response.status_code == 200
    assert isomorphic(Graph().parse(data=source.read_bytes(), format='json-ld'),
                      Graph().parse(data=response.content, format=syntax))
