import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from backend.ontology_service.merge_validation import RDF, OWL, explicit_conflicts

class MergeValidationTests(unittest.TestCase):
    def test_disjoint_membership_is_blocked(self):
        triples=[('a',RDF+'type','A'),('a',RDF+'type','B'),('A',OWL+'disjointWith','B')]
        self.assertEqual(explicit_conflicts(triples)[0]['kind'],'explicit_disjoint_membership')
    def test_typed_literals_with_equal_lexical_text_are_distinct_terms(self):
        from rdflib import Literal, URIRef
        from rdflib.namespace import XSD
        string, decimal = Literal('1', datatype=XSD.string), Literal('1', datatype=XSD.decimal)
        triples = [(string, URIRef(RDF+'type'), XSD.string),
                   (decimal, URIRef(RDF+'type'), XSD.decimal),
                   (XSD.string, URIRef(OWL+'disjointWith'), XSD.decimal)]
        self.assertEqual(explicit_conflicts(triples), [])

    def test_language_tags_and_blank_node_identity_are_preserved(self):
        from rdflib import Literal, BNode, URIRef
        triples = [(Literal('part', lang='en'), RDF+'type', 'A'),
                   (Literal('part', lang='fr'), RDF+'type', 'B'),
                   (BNode('entity'), RDF+'type', 'A'),
                   (URIRef('entity'), RDF+'type', 'B'), ('A', OWL+'disjointWith', 'B')]
        self.assertEqual(explicit_conflicts(triples), [])
        triples.append((Literal('part', lang='en'), RDF+'type', 'B'))
        self.assertEqual(explicit_conflicts(triples)[0]['subject'], '"part"@en')

    def test_object_and_data_property_collision_is_blocked(self):
        triples=[('p',RDF+'type',OWL+'ObjectProperty'),('p',RDF+'type',OWL+'DatatypeProperty')]
        self.assertEqual(explicit_conflicts(triples)[0]['kind'],'incompatible_property_kinds')
    def test_identity_conflict_is_symmetric(self):
        triples=[('a',OWL+'sameAs','b'),('b',OWL+'differentFrom','a')]
        self.assertEqual(explicit_conflicts(triples)[0]['kind'],'explicit_identity_contradiction')
    def test_explicit_impossibility(self):
        self.assertEqual(explicit_conflicts([('a',RDF+'type',OWL+'Nothing')])[0]['kind'],'instance_of_nothing')
        self.assertEqual(explicit_conflicts([('a',OWL+'differentFrom','a')])[0]['kind'],'self_difference')
    def test_unverified_legacy_preview_cannot_publish(self):
        tree=ast.parse(Path('backend/ontology_service/merge_service.py').read_text())
        cls=next(node for node in tree.body if isinstance(node,ast.ClassDef))
        fn=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='_apply')
        class Graph:
            def parse(self, **kwargs): return self
            def __iter__(self): return iter([('a',RDF+'type',OWL+'Nothing')])
        scope={'Any':object,'Graph':Graph,'__package__':'backend.ontology_service'}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<merge>','exec'),scope)
        writes=[]
        service=SimpleNamespace(registry=None,_load=lambda:{'preview':{'conflicts':[],'turtle':'retained'}},catalog=SimpleNamespace(register=lambda **kwargs:writes.append(kwargs)))
        with self.assertRaisesRegex(ValueError,'verified sources'):
            scope['_apply'](service,'preview','steward')
        self.assertEqual(writes,[])

    def test_same_labels_or_distinct_iris_are_not_equivalence(self):
        triples=[('a','label','Part'),('b','label','Part'),('a',RDF+'type','A'),('b',RDF+'type','B'),('A',OWL+'disjointWith','B')]
        self.assertEqual(explicit_conflicts(triples),[])

if __name__=='__main__':unittest.main()
