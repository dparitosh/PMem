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

if __name__ == '__main__': unittest.main()
