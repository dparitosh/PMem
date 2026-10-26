import ast
import asyncio
import hashlib
import logging
import pickle
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from backend.depo_platform.database_setup import verify_source_lookup_index
from backend.depo_platform.neo4j_setup import verify_indexes, REQUIRED_INDEXES
from backend.depo_platform.rdf_preparation import prepare_rdf
from backend.postgres_migrations import MIGRATIONS

class IndexRecoveryTests(unittest.TestCase):
    def test_missing_or_unreadable_artifact_is_unverified_without_graph_or_registry_write(self):
        tree=ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='ontology_publication_status')
        fn.decorator_list=[]
        for error in (FileNotFoundError('private-path'),PermissionError('private-path'),ValueError('private-path'),KeyError('private-path')):
            for retained in (None,{'publication_id':'old-digest','status':'published'}):
                records=SimpleNamespace(get=Mock(return_value=retained),compare_and_put=Mock())
                graph=Mock(side_effect=AssertionError('Graph must not be queried with an unverified digest'))
                async def thread(function,*args):return function(*args)
                scope={'__name__':'backend.ontology_service.router','graph_publications':records,
                    'catalog':SimpleNamespace(get=lambda _: {'ontology_id':'demo'},artifact_digest=Mock(side_effect=error)),
                    'run_in_threadpool':thread,'httpx':SimpleNamespace(AsyncClient=graph)}
                exec(compile(ast.Module(body=[fn],type_ignores=[]),'<status>','exec'),scope)
                result=asyncio.run(scope['ontology_publication_status']('demo',include_job=False))
                self.assertEqual(result['status'],'unverified')
                self.assertEqual(result['recovery_action'],'restore_retained_artifact' if isinstance(error,OSError) else 'review_retained_artifact')
                self.assertNotIn('private-path',str(result))
                records.compare_and_put.assert_not_called()
                graph.assert_not_called()

    def test_postgres_index_definition_and_validity_are_checked(self):
        cursor=SimpleNamespace(execute=Mock(),fetchone=Mock(return_value=(True,True,'depo_registry','namespace',"(value ->> 'source'::text)",'key')))
        verify_source_lookup_index(cursor,'semantic')
        cursor.fetchone.return_value=(False,True,'depo_registry','namespace',"value ->> 'source'",'key')
        with self.assertRaises(RuntimeError): verify_source_lookup_index(cursor,'semantic')
        cursor.fetchone.return_value=(True,True,'depo_registry','key',"value ->> 'source'",'namespace')
        with self.assertRaises(RuntimeError): verify_source_lookup_index(cursor,'semantic')
        self.assertIn(11, [v for v, _, _ in MIGRATIONS])

    def test_neo4j_indexes_must_be_online_with_expected_properties(self):
        rows=[{'name':name,'state':'ONLINE','type':'FULLTEXT' if isinstance(label,tuple) else 'TEXT' if name.startswith('idx_depo_resource_search_') else 'RANGE','labelsOrTypes':list(label) if isinstance(label,tuple) else [label],'properties':properties} for name,(label,properties) in REQUIRED_INDEXES.items()]
        self.assertEqual(verify_indexes(rows),sorted(REQUIRED_INDEXES))
        rows[0]['state']='POPULATING'
        with self.assertRaises(RuntimeError): verify_indexes(rows)
        rows[0]['state']='ONLINE'; rows[0]['properties']=['wrong']
        with self.assertRaises(RuntimeError): verify_indexes(rows)

    def test_parent_result_processing_observes_preparation_deadline(self):
        with patch('backend.depo_platform.rdf_preparation.time.monotonic',side_effect=[0,181]), patch('backend.depo_platform.rdf_preparation.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=pickle.dumps(b'ttl'))), patch.dict('os.environ',{'GRAPH_PUBLICATION_TIMEOUT_SECONDS':'180'}):
            with self.assertRaises(TimeoutError): prepare_rdf(b'rdf','xml')

    def test_missing_registry_receipt_uses_artifact_digest_under_guard(self):
        tree=ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='ontology_publication_status')
        fn.decorator_list=[]
        content=b'retained ontology'; digest=hashlib.sha256(content).hexdigest()
        scope=dict(__name__='backend.ontology_service.router',__package__='backend.ontology_service',hashlib=hashlib,graph_publications=SimpleNamespace(get=lambda key:None,put=Mock()),
            catalog=SimpleNamespace(get=lambda key:{'source':'engineering-workflow:old-source-hash'},artifact_digest=lambda key:digest),
            service_url=lambda *a:'http://graph',service_bearer_headers=lambda *a,**kw:{})
        async def thread(fn,*a):return fn(*a)
        urls=[]
        class Client:
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
            async def get(self,url,**kw):
                urls.append(url)
                return SimpleNamespace(status_code=200,raise_for_status=lambda:None,json=lambda:{'status':'published','current':True,'ontology_id':'demo','publication_id':digest,'resources':1,'relationships':0})
        scope.update(run_in_threadpool=thread,httpx=SimpleNamespace(AsyncClient=lambda **kw:Client(),HTTPError=RuntimeError))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<status>','exec'),scope)
        result=asyncio.run(scope['ontology_publication_status']('demo', include_job=False))
        self.assertTrue(urls[0].endswith('/'+digest))
        self.assertEqual(result['status'],'published')
        self.assertEqual([getattr(d,'id','') for d in next(n for n in ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8')).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='ontology_publication_status').decorator_list][-1],'ontology_writer')

    def test_slow_ollama_timeout_is_supported_consistently(self):
        from backend.core.ollama_auth import ollama_timeout
        for value in ('300','600','900'):
            with patch.dict('os.environ',{'LLM_REQUEST_TIMEOUT_SECONDS':value}):
                self.assertEqual(ollama_timeout(),float(value))
        for value in ('0','901','nan'):
            with patch.dict('os.environ',{'LLM_REQUEST_TIMEOUT_SECONDS':value}), self.assertRaises(ValueError):
                ollama_timeout()
