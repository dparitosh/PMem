import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

class MappingTests(unittest.TestCase):
    def test_mapping_preserves_iris_predicates_scope_and_truncation(self):
        tree=ast.parse(Path('backend/routes/ontology_routes.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='get_generic_mappings')
        fn.decorator_list=[]
        scope={'__package__':'backend.routes','Query':lambda **kw:kw['default'],'logger':logging.getLogger(__name__),'HTTPException':ValueError}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<mappings>','exec'),scope)
        calls=[]
        def query(text, params):
            calls.append((text,params))
            return [{'source_term':'urn:part','target_term':'urn:product','from_label':'Part','to_label':'Product','rel':'urn:exactMatch'}]*2
        modules={'backend.ontology_service.domain.taxonomy':SimpleNamespace(OntologyTaxonomyService=SimpleNamespace(_resolve_metadata=lambda key:{'ontology_id':'splm_id','prefix':'splm'})),
                 'backend.core.graph':SimpleNamespace(get_graph=lambda:SimpleNamespace(query=query))}
        with patch.dict('sys.modules',modules):
            result=asyncio.run(scope['get_generic_mappings']('splm_id','xsd',mapping_limit=1))
        self.assertTrue(result['truncated'])
        self.assertEqual(result['mapping_edges'][0]['source_term'],'urn:part')
        self.assertEqual(result['mapping_edges'][0]['mapping_type'],'urn:exactMatch')
        self.assertEqual(calls[0][1]['ontology_id'],'splm_id')
        self.assertEqual(calls[0][1]['mapping_limit'],2)
        self.assertNotIn('labels(a)[0]',calls[0][0])
        self.assertIn('http://www.w3.org/2004/02/skos/core#exactMatch', calls[0][1]['alignment_predicates'])
        self.assertIn('OR r.predicate IN $alignment_predicates', calls[0][0])
