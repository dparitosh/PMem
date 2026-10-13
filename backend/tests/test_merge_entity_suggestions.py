import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import hashlib


class SuggestionTests(unittest.TestCase):
    def test_source_locks_are_ordered_and_cover_the_application(self):
        tree = ast.parse(Path('backend/ontology_service/merge_service.py').read_text(encoding='utf-8'))
        fn = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == '_with_source_locks')
        scope = {}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<locks>','exec'),scope)
        events=[]
        def lock(identifier, operation):
            events.append(('lock',identifier))
            try: return operation()
            finally: events.append(('unlock',identifier))
        service=SimpleNamespace(registry=None,_load=lambda:{'preview':{'source_ontology_ids':['b','a']}},catalog=SimpleNamespace(get=lambda key:{},with_publication_lock=lock))
        scope[fn.name](service,'preview',lambda:events.append(('apply',None)))
        self.assertEqual(events,[('lock','a'),('lock','b'),('apply',None),('unlock','b'),('unlock','a')])
        service.catalog.get=lambda key:None
        with self.assertRaisesRegex(ValueError,'Migrate legacy'):
            scope[fn.name](service,'preview',lambda: self.fail('must not apply'))

    def test_changed_source_blocks_apply_before_registration(self):
        tree = ast.parse(Path('backend/ontology_service/merge_service.py').read_text(encoding='utf-8'))
        fn = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == '_apply')
        scope = {'Any':object,'hashlib':hashlib}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<apply>','exec'),scope)
        calls=[]
        record={'conflicts':[], 'sources':[{'ontology_id':'first','artifact_sha256':hashlib.sha256(b'original').hexdigest()}]}
        catalog=SimpleNamespace(get=lambda key: {},read_artifact=lambda key: ({},b'changed'),register=lambda **kw:calls.append(kw))
        service=SimpleNamespace(registry=None,_load=lambda:{'preview':record},catalog=catalog)
        with self.assertRaisesRegex(ValueError,'source changed'):
            scope[fn.name](service,'preview','steward')
        self.assertEqual(calls,[])

    def test_only_unambiguous_same_kind_matches_are_suggested(self):
        tree = ast.parse(Path('backend/ontology_service/merge_service.py').read_text(encoding='utf-8'))
        fn = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == '_entity_suggestions')
        fn.decorator_list = []
        scope = dict(OWL=SimpleNamespace(Class='class',ObjectProperty='object',DatatypeProperty='data',AnnotationProperty='annotation'), RDFS=SimpleNamespace(Class='rdfsClass',label='label',comment='comment',domain='domain',range='range'), RDF=SimpleNamespace(type='type'), URIRef=str)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<suggestions>','exec'),scope)
        class Graph:
            def __init__(self,rows): self.rows=rows
            def subject_objects(self,predicate): return [(uri,kind) for uri,kind,label in self.rows]
            def objects(self,uri,predicate):
                if predicate == 'type': return [kind for identifier,kind,label in self.rows if identifier==uri]
                if predicate != 'label': return []
                class Label(str):
                    def n3(self): return str(self)
                return [Label(label) for identifier,kind,label in self.rows if identifier==uri]
        left=Graph([('urn:a','class','Part'),('urn:b','class','Duplicate'),('urn:c','class','Duplicate'),('urn:d','object','Code')])
        right=Graph([('urn:x','class','part'),('urn:y','class','Duplicate'),('urn:z','data','Code')])
        result=scope[fn.name](left,right)
        self.assertEqual(len(result),1)
        self.assertEqual((result[0]['source_iri'],result[0]['target_iri']),('urn:a','urn:x'))
        self.assertIn('review',result[0]['reason'])


if __name__ == '__main__': unittest.main()
