import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock
from backend.mesh_store import PostgresRegistry, InMemoryRegistry

class IntegrationBlockerTests(TestCase):
    def test_insert_only_conflict_cannot_overwrite(self):
        registry = PostgresRegistry('data_job_definitions')
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        @contextmanager
        def connect(): yield connection
        registry._connect = connect
        cursor.fetchone.return_value = ({'owner':'first'},)
        self.assertEqual(registry.create('job:1', {'owner':'first'}), {'owner':'first'})
        sql = cursor.execute.call_args.args[0]
        self.assertIn('DO NOTHING RETURNING value', sql)
        self.assertNotIn('DO UPDATE', sql)
        cursor.fetchone.return_value = None
        with self.assertRaises(FileExistsError): registry.create('job:1', {'owner':'second'})
    def test_job_creation_calls_atomic_create_without_get(self):
        node = next(n for n in ast.parse(Path('backend/data_pipeline_service/job_definitions.py').read_text()).body if isinstance(n, ast.FunctionDef) and n.name=='create')
        store = InMemoryRegistry()
        scope = {'Any':object, 'validate_definition':lambda p:[], 'handler_registry':SimpleNamespace(contracts=lambda:{'type':('input','output')}), 'now':lambda:'now','store':store,'key':lambda a,b:a+':'+b}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'create','exec'),scope)
        payload={'job_id':'job','name':'job','version':'1','owner':'first','job_type':'type','quality_profile':'quality'}
        scope['create'](payload)
        with self.assertRaises(FileExistsError): scope['create']({**payload,'owner':'second'})
        self.assertEqual(store.get('job:1')['owner'],'first')
    def test_author_identity_overrides_payload_owner_and_failure_prevents_write(self):
        node = next(n for n in ast.parse(Path('backend/data_pipeline_service/router.py').read_text()).body if isinstance(n, ast.FunctionDef) and n.name=='create_job_definition')
        node.decorator_list=[]
        calls=[]
        def authorize(request, **kwargs):
            self.assertEqual(kwargs['token_env'],'DATA_JOB_APPROVAL_TOKEN')
            if request!='authorized': raise PermissionError('rejected')
            return 'server-actor'
        scope={'Any':object,'Request':object,'service_write_identity':authorize,'job_definitions':SimpleNamespace(create=lambda p:calls.append(p) or p)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'router','exec'),scope)
        with self.assertRaises(PermissionError): scope['create_job_definition']({'owner':'spoofed'},'anonymous')
        self.assertEqual(calls,[])
        self.assertEqual(scope['create_job_definition']({'owner':'spoofed'},'authorized')['owner'],'server-actor')
    def test_every_factory_app_has_protected_access(self):
        tree=ast.parse(Path('backend/depo_platform/service_runtime.py').read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='authenticated_access')
        self.assertEqual(ast.unparse(node.args.defaults[0]),'Depends(graph_read_identity)')

if __name__=='__main__': main()
