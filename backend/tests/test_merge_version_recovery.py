import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest

class MergeVersionRecoveryTests(unittest.TestCase):
    def method(self):
        tree=ast.parse(Path('backend/ontology_service/intelligence.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='create_merge_version')
        scope={'Any':object}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<version>','exec'),scope)
        return scope['create_merge_version']
    def test_retry_reuses_persisted_snapshot_without_creating_another(self):
        snapshots={}; calls=[]
        def create(**kwargs):
            calls.append(kwargs); snapshot={'version_id':'retained'}
            snapshots['version:'+kwargs['label']]=snapshot
            return snapshot
        service=SimpleNamespace(registry=SimpleNamespace(get=snapshots.get),create_version=create)
        fn=self.method()
        first=fn(service,ontology={'ontology_id':'merged-1'},author='original')
        retry=fn(service,ontology={'ontology_id':'merged-1'},author='retry-operator')
        self.assertEqual(first,retry); self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['author'],'original')
    def test_merge_retry_keeps_original_approval_after_version_failure(self):
        tree=ast.parse(Path('backend/ontology_service/merge_service.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_apply')
        class Graph:
            def parse(self,**kwargs):return self
            def __iter__(self):return iter([])
        scope={'Any':object,'Graph':Graph,'hashlib':hashlib,'__package__':'backend.ontology_service'}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<merge>','exec'),scope)
        values={'p':{'conflicts':[],'turtle':'rdf','prefix':'m','ontology_name':'Merged','description':'','source_ontology_ids':['a','b'],'triple_count':1}}
        actors=[]
        def register(**kwargs):
            actors.append(kwargs['extra_metadata']['provenance']['approved_by'])
            return {'ontology_id':'merged','provenance':kwargs['extra_metadata']['provenance']}
        attempts=[]
        def version(**kwargs):
            attempts.append(kwargs['author'])
            if len(attempts)==1:raise OSError('version persistence unavailable')
            return {'version_id':'v'}
        service=SimpleNamespace(registry=None,_load=lambda:values,_save=lambda *args:None,
            catalog=SimpleNamespace(register=register),intelligence=SimpleNamespace(create_merge_version=version))
        with self.assertRaises(OSError):scope['_apply'](service,'p','first-steward')
        result=scope['_apply'](service,'p','retry-steward')
        self.assertEqual(result['status'],'merged')
        self.assertEqual(actors,['first-steward','first-steward'])
        self.assertEqual(attempts,['first-steward','first-steward'])

    def test_missing_identity_is_rejected(self):
        with self.assertRaises(ValueError):self.method()(None,ontology={},author='steward')

if __name__=='__main__':unittest.main()
