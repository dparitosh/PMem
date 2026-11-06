"""Offline regression checks for mapping; no publication or live database access."""
import pytest
from rdflib import Graph, Namespace, Literal
from rdflib.namespace import OWL, RDF, RDFS, XSD
from backend.Services.ontology_mapping_service import OntologyMappingService as Mapping, TargetOntologyRegistry, EntityMapping

@pytest.mark.parametrize('left,right,minimum', [
    ('product_definition','product_definition',1.0),
    ('product_definition','Product',0.85),
    ('part_design','part_definition',0.6),
    ('assembly_item','assembly',0.85),
    ('representation_item','representation',0.85),
])
def test_string_similarity(left, right, minimum):
    score = Mapping.string_similarity(left, right)
    assert minimum <= score <= 1
    assert Mapping.string_similarity(right, left) == score

@pytest.mark.parametrize('name,expected', [
    ('product_definition','product'), ('source_product_definition','product'),
    ('product_definition_type','product_definition'), ('PRODUCT_DEFINITION','product'),
    ('impl_product','product'), ('abstract_representation','representation'),
])
def test_normalize_name(name, expected):
    assert Mapping.normalize_name(name) == expected


def test_entity_similarity_keeps_identity_and_rejects_unmatched():
    sources = ['product_definition', 'cartesian_point', 'zzzzzzzzzz']
    targets = TargetOntologyRegistry.get_ontology('ap242_product')['entities']
    matches = Mapping.find_similar_entities(sources, targets, threshold=0.9)
    assert matches == [('product_definition','product_definition',1.0), ('cartesian_point','cartesian_point',1.0)]
    assert Mapping.find_similar_entities(sources, [], threshold=0.9) == []


def test_target_ontologies_have_usable_namespaces_and_entities():
    names = TargetOntologyRegistry.list_ontologies()
    assert 'ap242_product' in names
    for name in names:
        ontology = TargetOntologyRegistry.get_ontology(name)
        assert ontology['namespace'].startswith(('http://','https://'))
        assert ontology['entities'] and len(ontology['entities']) == len(set(ontology['entities']))
    assert TargetOntologyRegistry.get_ontology('unknown-fixture') is None


def test_mapping_report_counts_coverage_and_confidence():
    mappings = [EntityMapping('part','Part',0.95,'exact',{'id':'identifier'}),
                EntityMapping('item','Item',0.85,'similar')]
    report = Mapping.generate_mapping_report(mappings, ['context','coordinate'])
    assert (report['total_entities'],report['mapped_entities'],report['unmapped_entities']) == (4,2,2)
    assert report['coverage'] == 0.5
    assert report['average_confidence'] == pytest.approx(0.9)
    assert (report['high_confidence_mappings'],report['medium_confidence_mappings'],report['low_confidence_mappings']) == (1,1,0)
    assert report['mappings'][0]['source'] == 'part'
    assert report['mappings'][0]['property_count'] == 1
    empty = Mapping.generate_mapping_report([], [])
    assert empty['coverage'] == empty['average_confidence'] == 0


def test_owl_alignment_preserves_unmapped_terms_and_literals():
    source = Namespace('https://source.example/#')
    target = Namespace('https://target.example/#')
    graph = Graph()
    graph.add((source.part, RDF.type, OWL.Class))
    graph.add((source.part, RDFS.label, Literal(str(source.part))))
    graph.add((source.part_id, RDF.type, OWL.DatatypeProperty))
    graph.add((source.part_id, RDFS.domain, source.part))
    graph.add((source.part_id, RDFS.range, XSD.string))
    graph.add((source.Unmapped, RDF.type, OWL.Class))
    aligned = Mapping.align_owl_namespaces(graph.serialize(format='turtle'), str(source), str(target),
        [EntityMapping('part','Part',0.95,'reviewed',{'id':'identifier'})])
    result = Graph().parse(data=aligned, format='turtle')
    assert (target.Part, RDF.type, OWL.Class) in result
    assert (target.Part_identifier, RDFS.domain, target.Part) in result
    assert (target.Part_identifier, RDFS.range, XSD.string) in result
    assert (target.Part, RDFS.label, Literal(str(source.part))) in result
    assert (source.Unmapped, RDF.type, OWL.Class) in result
    assert not list(result.triples((None, OWL.equivalentClass, None)))
    assert len(result) == len(graph)
