import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Any, List
import unittest
import sys
from unittest.mock import patch


class InferencePreviewTests(unittest.TestCase):
    def test_failed_rdf_parse_cannot_contaminate_the_next_format(self):
        class URI(str): pass
        owl=SimpleNamespace(equivalentClass='class',equivalentProperty='property',sameAs='same',disjointWith='disjoint')
        class Graph:
            def __init__(self): self.rows=[]
            def parse(self,path,format):
                if format=='turtle':
                    self.rows.append((URI('bad'), 'same', URI('leaked')))
                    raise ValueError('partial parse')
                self.rows.append((URI('good'),'same',URI('target')))
            def triples(self,pattern): return [row for row in self.rows if row[1]==pattern[1]]
        with patch.dict(sys.modules,{'rdflib':SimpleNamespace(Graph=Graph,URIRef=URI),
            'rdflib.namespace':SimpleNamespace(OWL=owl,SKOS=SimpleNamespace(exactMatch='exact'))}):
            result=self.preview({},['equivalence'])
        self.assertEqual([(item['subject'],item['object']) for item in result['inferences']],[('target','good')])

    def preview(self, reasoning, enabled):
        tree = ast.parse(Path('backend/ontology_service/domain/reasoning.py').read_text(encoding='utf-8'))
        fn = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'preview_inferences')
        fn.decorator_list = []
        scope = dict(__package__='backend.ontology_service.domain', Dict=Dict,Any=Any,List=List)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<inference>','exec'),scope)
        service=SimpleNamespace(semantic_context=lambda identifier:{'file_path':'missing.ttl'},inspect_context=lambda ctx:reasoning,
            _ref_key=lambda value: str(value or ''), _ref_label=lambda value:str(value), _entry_label=lambda value:value.get('label',''))
        rules={key:key in enabled for key in ['transitive_subclass','domain_range_typing','equivalence','disjointness','individual_type_closure']}
        return scope[fn.name](service,'ontology',{'rules':rules,'limit':25})

    def test_disjointness_detects_inherited_types(self):
        result=self.preview({'subclass_edges':[{'source':'Child','target':'Parent'}],
            'individuals':[{'iri':'instance','types':['Child','Other']}],
            'disjoint_edges':[{'source':'Parent','target':'Other'}]},['disjointness'])
        self.assertEqual(result['inferences'][0]['rule'],'disjointness_violation')
        self.assertIsNone(result['inferences'][0]['confidence'])

    def test_equivalence_predicates_remain_distinct(self):
        result=self.preview({'same_as_edges':[{'source':'a','target':'b'}],
            'skos_exact_match_edges':[{'source':'c','target':'d'}]},['equivalence'])
        self.assertEqual({item['predicate'] for item in result['inferences']},{'owl:sameAs','skos:exactMatch'})

    def test_closure_is_deterministic_and_excludes_self_cycles(self):
        edges=[{'source':'A','target':'B'},{'source':'B','target':'C'},{'source':'C','target':'A'}]
        first=self.preview({'subclass_edges':edges},['transitive_subclass'])
        second=self.preview({'subclass_edges':list(reversed(edges))},['transitive_subclass'])
        self.assertEqual(first['inferences'],second['inferences'])
        self.assertTrue(all(item['subject'] != item['object'] for item in first['inferences']))

    def test_domain_range_is_bounded_and_not_claimed_as_instance_inference(self):
        result=self.preview({'object_properties':[{'iri':'property','domain':[str(i) for i in range(50)],'range':['target']}]},['domain_range_typing'])
        self.assertEqual(len(result['constraints']),25)
        self.assertEqual(result['inferences'],[])
        self.assertTrue(result['summary']['truncated'])


if __name__ == '__main__': unittest.main()
