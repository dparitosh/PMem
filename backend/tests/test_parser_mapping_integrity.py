import unittest
from rdflib import Graph, Namespace, RDF, RDFS, Literal
from rdflib.namespace import OWL
from parsers.xsd_parser import XSDParser
from mapping.semantic_mapper import SemanticMapper
from backend.Services.ontology_mapping_service import OntologyMappingService as Service, EntityMapping


class ParserMappingIntegrityTests(unittest.TestCase):
    def test_alignment_updates_references_and_preserves_unmapped_and_literals(self):
        source = '''@prefix ex: <http://source/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Part a owl:Class . ex:Unmapped a owl:Class .
ex:Child rdfs:subClassOf ex:Part ; rdfs:label "ex:Part" .'''
        result = Graph().parse(data=Service.align_owl_namespaces(source, 'http://source/', 'http://target/',
                              [EntityMapping('Part', 'Component', .9, 'test')]), format='turtle')
        src, target = Namespace('http://source/'), Namespace('http://target/')
        self.assertIn((src.Child, RDFS.subClassOf, target.Component), result)
        self.assertIn((src.Unmapped, RDF.type, OWL.Class), result)
        self.assertIn((src.Child, RDFS.label, Literal('ex:Part')), result)
        self.assertFalse(list(result.triples((None, OWL.equivalentClass, None))))

    def test_constraint_conflicts_and_input_immutability(self):
        target = {'cardinality_bounds': {'p': {'min': 0, 'max': 1}}, 'unique_constraints': ['id']}
        with self.assertRaises(ValueError):
            Service.merge_constraints({'cardinality_bounds': {'p': {'min': 2}}}, target)
        result = Service.merge_constraints({'unique_constraints': ['name']}, target)
        self.assertEqual(target['unique_constraints'], ['id'])
        result['cardinality_bounds']['p']['min'] = 9
        self.assertEqual(target['cardinality_bounds']['p']['min'], 0)

    def test_xsd_preserves_local_elements_and_builtin_datatypes(self):
        source = b'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="A"><xs:sequence><xs:element name="id" type="xs:string"/></xs:sequence></xs:complexType>
<xs:complexType name="B"><xs:sequence><xs:element name="id" type="xs:integer"/></xs:sequence></xs:complexType></xs:schema>'''
        model = XSDParser.parse_bytes(source)
        self.assertEqual(len(model['elements']), 2)
        self.assertEqual(model, XSDParser.parse_bytes(source))
        graph = XSDParser.model_to_source_graph(model)
        self.assertEqual(len(list(graph.subjects(RDF.type, OWL.DatatypeProperty))), 2)
        self.assertFalse(list(graph.subjects(RDF.type, OWL.ObjectProperty)))

    def test_xsd_rejects_dtd_and_non_schema(self):
        for source in (b'<!DOCTYPE schema [<!ENTITY x "test">]><schema/>', b'<root/>'):
            with self.assertRaises(ValueError): XSDParser.parse_bytes(source)

    def test_mapping_requires_canonical_graph_and_retains_ambiguity(self):
        source, canonical = Graph(), Graph()
        ns = Namespace('http://example/')
        for graph, subject in ((source, ns.Source), (canonical, ns.A), (canonical, ns.B)):
            graph.add((subject, RDF.type, OWL.Class)); graph.add((subject, RDFS.label, Literal('Part')))
        with self.assertRaises(ValueError): SemanticMapper.align_source_to_canonical(source)
        proposals = SemanticMapper.align_source_to_canonical(source, canonical)
        self.assertEqual(proposals[str(ns.Source)]['targets'], [str(ns.A), str(ns.B)])
        self.assertEqual(proposals[str(ns.Source)]['status'], 'requires_review')
