import ast
import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from backend.depo_platform.neo4j_setup import CONSTRAINT_DEFINITIONS, verify_constraints


class AuditRegressions(unittest.TestCase):
    def test_constraint_names_cannot_hide_incompatible_definitions(self):
        rows = [{'name':name,'type':'UNIQUENESS','entityType':'NODE','labelsOrTypes':[label],'properties':properties}
                for name,(label,properties) in CONSTRAINT_DEFINITIONS.items()]
        self.assertEqual(verify_constraints(rows), sorted(CONSTRAINT_DEFINITIONS))
        for field,value in [('type','NODE_PROPERTY_EXISTENCE'),('entityType','RELATIONSHIP'),('labelsOrTypes',['Wrong']),('properties',['wrong'])]:
            changed = [dict(row) for row in rows]
            changed[0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError,'Incompatible'):
                verify_constraints(changed)

    def test_label_choice_is_independent_of_iteration_order(self):
        class Label(str):
            def __new__(cls,text,language=None):
                obj = str.__new__(cls,text); obj.language=language; return obj
        tree=ast.parse(Path('backend/depo_platform/projection_preparation.py').read_text())
        fn=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='build_projection')
        start=next(i for i,node in enumerate(fn.body) if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='label_rows' for t in node.targets))
        code=compile(ast.Module(body=fn.body[start:start+3],type_ignores=[]),'<labels>','exec')
        rows=[('urn:a',Label('Zulu','en')),('urn:a',Label('Alpha','en')),('urn:a',Label('Other')),('urn:a',Label('Autre','fr'))]
        for ordered in [rows,list(reversed(rows))]:
            scope={'rdf_graph':SimpleNamespace(subject_objects=lambda _:ordered),'RDFS':SimpleNamespace(label='label')}
            exec(code,scope)
            self.assertEqual(scope['labels'],{'urn:a':'Alpha'})

    def test_verifier_cannot_overwrite_newer_publication(self):
        tree=ast.parse(Path('backend/ontology_service/router.py').read_text())
        fn=next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='ontology_publication_status')
        fn.decorator_list=[]
        content=b'test'; digest=hashlib.sha256(content).hexdigest()
        old={'ontology_id':'demo','publication_id':digest,'status':'unverified'}
        newer={**old,'status':'publishing','attempt':'new'}
        values={'demo':old}; comparisons=[]
        def compare(key,expected,value):
            comparisons.append(expected)
            if values[key] != expected: return False
            values[key]=value; return True
        class Client:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def get(self,*args,**kwargs):
                values['demo']=newer
                return SimpleNamespace(status_code=200,raise_for_status=lambda:None,json=lambda:{'ontology_id':'demo','publication_id':digest,'status':'published','current':True,'resources':1,'relationships':0})
        async def thread(function,*args):return function(*args)
        scope={'__name__':'backend.ontology_service.router','__package__':'backend.ontology_service',
               'hashlib':hashlib,'graph_publications':SimpleNamespace(get=lambda key:values[key],compare_and_put=compare),
               'catalog':SimpleNamespace(read_artifact=lambda _:({},content),artifact_digest=lambda _:digest), 'run_in_threadpool':thread,
               'service_url':lambda *args:'http://graph','service_bearer_headers':lambda *args,**kwargs:{},
               'httpx':SimpleNamespace(AsyncClient=lambda **kwargs:Client(),HTTPError=RuntimeError)}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<status>','exec'),scope)
        result=asyncio.run(scope['ontology_publication_status']('demo', include_job=False))
        self.assertEqual(result['status'],'unverified')
        self.assertEqual(values['demo'],newer)
        self.assertEqual(comparisons,[old])
