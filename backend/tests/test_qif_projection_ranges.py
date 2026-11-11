from pathlib import Path

import pytest
from rdflib import Graph, RDF, RDFS, URIRef
from rdflib.namespace import DC, OWL, XSD

from backend.qif.ontology_builder import inspect_schema_set
from backend.qif.rdf_projection import project_schema_ontology


def schema(tmp_path, body, name='schema.xsd', namespace='urn:qif:test', extra=''):
    path = tmp_path / name
    path.write_text(f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="{namespace}" targetNamespace="{namespace}" {extra}>{body}</xs:schema>')
    return path


def project(paths):
    inspection = inspect_schema_set(paths)
    data, summary = project_schema_ontology(inspection, 'test')
    return Graph().parse(data=data, format='turtle'), summary


def test_global_reference_resolves_complex_type_and_source_identity(tmp_path):
    shared = schema(tmp_path, '<xs:complexType name="PartType"/><xs:element name="Part" type="t:PartType"/>', 'shared.xsd', 'urn:shared')
    owner = schema(tmp_path, '<xs:complexType name="Assembly"><xs:sequence><xs:element ref="s:Part"/></xs:sequence></xs:complexType>', extra='xmlns:s="urn:shared"')
    graph, _ = project([shared, owner])
    prop = URIRef('urn:qif:test#property/Assembly/Part')
    assert (prop, RDF.type, OWL.ObjectProperty) in graph
    assert (prop, RDF.type, OWL.DatatypeProperty) not in graph
    assert (prop, RDFS.range, URIRef('urn:shared#PartType')) in graph
    assert (URIRef('urn:shared#Part'), RDFS.subClassOf, URIRef('urn:shared#PartType')) in graph
    assert list(graph.objects(prop, DC.source))
    assert list(graph.objects(prop, RDFS.comment))


def test_list_lexical_projection_does_not_claim_scalar_item_equivalence(tmp_path):
    path = schema(tmp_path, '<xs:simpleType name="Vector"><xs:list itemType="xs:double"/></xs:simpleType><xs:simpleType name="Point"><xs:restriction base="t:Vector"><xs:length value="3"/></xs:restriction></xs:simpleType><xs:complexType name="Position"><xs:attribute name="value" type="t:Point"/></xs:complexType>')
    graph, summary = project([path])
    prop = URIRef('urn:qif:test#property/Position/value')
    assert (prop, RDFS.range, XSD.string) in graph
    assert (prop, RDFS.range, XSD.double) not in graph
    assert (URIRef('urn:qif:test#Vector'), RDF.type, RDFS.Datatype) in graph
    assert (URIRef('urn:qif:test#Vector'), RDF.type, OWL.Class) not in graph
    assert summary['lexical_list_types'] == ['Vector']
    assert any('lexical representation' in text for text in summary['limitations'])


def test_element_type_name_collision_keeps_separate_declarations(tmp_path):
    path = schema(tmp_path, '<xs:complexType name="Part"/><xs:element name="Part" type="t:Part"/>')
    graph, _ = project([path])
    assert (URIRef('urn:qif:test#element/Part'), RDFS.subClassOf, URIRef('urn:qif:test#Part')) in graph


@pytest.mark.parametrize('declaration', ['<xs:element ref="t:Missing"/>', '<xs:element name="unknown"/>', '<xs:element name="unknown" type="t:Missing"/>'])
def test_unknown_reference_or_type_fails_instead_of_emitting_rangeless_property(tmp_path, declaration):
    path = schema(tmp_path, f'<xs:complexType name="Part"><xs:sequence>{declaration}</xs:sequence></xs:complexType>')
    with pytest.raises(ValueError, match='Unresolved|explicit supported type'):
        project([path])


def test_owner_lookup_preserves_distinct_properties(tmp_path):
    path = schema(tmp_path, '<xs:complexType name="A"><xs:attribute name="id" type="xs:int"/></xs:complexType><xs:complexType name="B"><xs:attribute name="id" type="xs:string"/></xs:complexType>')
    graph, _ = project([path])
    assert (URIRef('urn:qif:test#property/A/id'), RDFS.range, XSD.int) in graph
    assert (URIRef('urn:qif:test#property/B/id'), RDFS.range, XSD.string) in graph


def test_complete_bundled_qif_set_resolves_every_projected_property():
    paths = list((Path(__file__).resolve().parents[2] / 'docs' / 'xsd').rglob('*.xsd'))
    assert len(paths) >= 23
    graph, summary = project(paths)
    properties = set(graph.subjects(RDF.type, OWL.ObjectProperty)) | set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    assert len(properties) == summary['properties_created']
    assert len(properties) > 4000
    assert all(list(graph.objects(prop, RDFS.range)) for prop in properties)
    assert all(list(graph.objects(prop, DC.source)) for prop in properties)
