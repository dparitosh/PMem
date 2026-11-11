"""Annotations and instance declarations must survive graph preparation."""
import json
from rdflib import Graph
from backend.depo_platform.ontology_semantics import inventory
from backend.depo_platform.projection_preparation import build_projection


def test_annotations_exist_without_local_annotation_property_declarations():
    graph = Graph().parse(data='''
      @prefix ex: <urn:test:> .
      @prefix owl: <http://www.w3.org/2002/07/owl#> .
      @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
      ex:Part a owl:Class ; rdfs:label "Part"@en ; rdfs:comment "Physical engineering item" .
    ''', format='turtle')
    assert inventory(graph)['annotation_properties'] == 0
    rows, _, _ = build_projection(graph)
    part = next(row for row in rows if row['iri'] == 'urn:test:Part')
    annotations = json.loads(part['rdf_properties'])
    assert annotations['http://www.w3.org/2000/01/rdf-schema#label'][0] == {
        'value': 'Part', 'language': 'en', 'datatype': None}
    assert part['description'] == 'Physical engineering item'


def test_declared_annotation_properties_and_individuals_are_separate_from_domain_typing():
    graph = Graph().parse(data='''
      @prefix ex: <urn:test:> .
      @prefix owl: <http://www.w3.org/2002/07/owl#> .
      ex:Part a owl:Class .
      ex:note a owl:AnnotationProperty .
      ex:relatedNote a owl:AnnotationProperty .
      ex:one a ex:Part ; ex:note "Approved design"@en ; ex:relatedNote ex:two .
      ex:two a ex:Part, owl:NamedIndividual .
    ''', format='turtle')
    counts = inventory(graph)
    assert counts['annotation_properties'] == 2
    assert counts['named_individuals'] == 1
    assert counts['individuals'] == 2
    rows, relationships, _ = build_projection(graph)
    by_id = {row['iri']: row for row in rows}
    assert by_id['urn:test:one']['kind'] == 'individual'
    assert 'http://www.w3.org/2002/07/owl#NamedIndividual' not in by_id['urn:test:one']['rdf_types']
    assert 'http://www.w3.org/2002/07/owl#NamedIndividual' in by_id['urn:test:two']['rdf_types']
    assert json.loads(by_id['urn:test:one']['rdf_properties'])['urn:test:note'][0]['value'] == 'Approved design'
    assert {'source':'urn:test:one', 'target':'urn:test:two', 'predicate':'urn:test:relatedNote'} in relationships['SEMANTIC_RELATION']
