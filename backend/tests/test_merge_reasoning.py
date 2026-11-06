import unittest
from rdflib import Graph, BNode, URIRef, Literal, RDF, OWL, RDFS
from rdflib.compare import isomorphic
from owlrl import DeductiveClosure, OWLRL_Semantics
from backend.ontology_service.merge_reasoning import expand_owlrl, _IndexedBlankNodes


PREFIXES = '''@prefix : <urn:test:> .
@prefix owl:<http://www.w3.org/2002/07/owl#> .
@prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:<http://www.w3.org/2001/XMLSchema#> . '''


class MergeReasoningTests(unittest.TestCase):
    def test_closure_matches_upstream_across_rule_families(self):
        cases = [
            ':A a owl:Class; rdfs:subClassOf :B . :B rdfs:subClassOf :C . :x a :A .',
            ':p a owl:TransitiveProperty . :x :p :y . :y :p :z .',
            ':p owl:inverseOf :q; rdfs:domain :A; rdfs:range :B . :x :p :y .',
            ':p a owl:FunctionalProperty . :x :p :y,:z . :y owl:differentFrom :z .',
            ':p a owl:InverseFunctionalProperty . :x :p :v . :y :p :v .',
            ':x owl:sameAs :y . :x :p :v . :z :p :y .',
            ':p owl:propertyChainAxiom (:a :b) . :x :a :y . :y :b :z .',
            ':R a owl:Restriction; owl:onProperty :p; owl:someValuesFrom :A . :x :p :y . :y a :A .',
            ':R a owl:Restriction; owl:onProperty :p; owl:allValuesFrom :A . :x a :R; :p :y .',
            ':R a owl:Restriction; owl:onProperty :p; owl:hasValue :v . :x a :R . :y :p :v .',
            ':A owl:intersectionOf (:B :C) . :x a :B,:C . :D owl:unionOf (:B :C) .',
            ':A owl:oneOf (:x :y) . :A owl:disjointWith :B . :x a :B .',
            ':x :p "1"^^xsd:integer, "2"^^xsd:decimal .',
            ':A rdfs:subClassOf [a owl:Restriction; owl:onProperty :p; owl:maxCardinality 1] . :x a :A; :p :v,:w .',
        ]
        for source in cases:
            with self.subTest(source=source):
                base = Graph().parse(data=PREFIXES+source, format='turtle')
                optimized = Graph()
                for triple in base: optimized.add(triple)
                DeductiveClosure(OWLRL_Semantics).expand(base)
                expand_owlrl(optimized)
                self.assertTrue(isomorphic(base, optimized))

    def test_blank_predicate_cleanup_and_shared_restrictions_match_upstream(self):
        base = Graph()
        for index in range(40):
            node = BNode(str(index))
            base.add((URIRef(f'urn:c{index}'), RDFS.subClassOf, node))
            base.add((node, RDF.type, OWL.Restriction))
            base.add((node, OWL.onProperty, URIRef('urn:p')))
            base.add((node, OWL.someValuesFrom, URIRef('urn:A')))
        base.add((URIRef('urn:x'), BNode('predicate'), Literal('value')))
        optimized = Graph()
        for triple in base: optimized.add(triple)
        DeductiveClosure(OWLRL_Semantics).expand(base)
        expand_owlrl(optimized)
        self.assertTrue(isomorphic(base, optimized))
        self.assertFalse(any(isinstance(p, BNode) for _, p, _ in optimized))

    def test_index_preserves_order_and_avoids_linear_equality_scans(self):
        class CountedNode(BNode):
            comparisons = 0
            __hash__ = BNode.__hash__
            def __eq__(self, other):
                type(self).comparisons += 1
                return super().__eq__(other)
        nodes = [CountedNode(str(index)) for index in range(4000)]
        indexed = _IndexedBlankNodes()
        for node in nodes:
            if node not in indexed: indexed.append(node)
        for node in nodes: self.assertIn(node, indexed)
        self.assertEqual(list(indexed), nodes)
        self.assertLess(CountedNode.comparisons, 100)

    def test_split_reasoning_and_shacl_matches_original_pipeline(self):
        from pyshacl import validate
        original = Graph().parse(data=PREFIXES+''':p owl:inverseOf :q .
            :q rdfs:domain :B . :x :p :y .''', format='turtle')
        optimized = Graph()
        for prefix, namespace in original.namespaces(): optimized.bind(prefix, namespace)
        for triple in original: optimized.add(triple)
        shapes = Graph().parse(data='''@prefix sh:<http://www.w3.org/ns/shacl#> .
            <urn:shape> a sh:NodeShape; sh:targetClass <urn:test:B>;
            sh:property [sh:path <urn:required>; sh:minCount 1] .''', format='turtle')
        baseline = validate(original, shacl_graph=shapes, inference='owlrl', inplace=True,
                            allow_infos=False, allow_warnings=False, advanced=False, do_owl_imports=False)
        expand_owlrl(optimized)
        actual = validate(optimized, shacl_graph=shapes, inference='none', inplace=True,
                          allow_infos=False, allow_warnings=False, advanced=False, do_owl_imports=False)
        self.assertFalse(actual[0])  # The inferred B instance must be checked.
        self.assertEqual(actual[0], baseline[0])
        self.assertTrue(isomorphic(original, optimized))
        self.assertTrue(isomorphic(actual[1], baseline[1]))
