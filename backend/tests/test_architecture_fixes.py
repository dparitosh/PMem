import ast
import asyncio
import os
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import MagicMock
from backend.depo_platform.execution_guard import guarded_execution, ensure_execution_allowed
from backend.mesh_store import PostgresRegistry, InMemoryRegistry
from backend.artifact_store import ArtifactStore

class ArchitectureTests(TestCase):
    def test_lease_loss_blocks_artifact_and_registry_persistence(self):
        state = {'lost': False}
        def guard():
            if state['lost']: raise RuntimeError('lease lost')
        with TemporaryDirectory() as root:
            store=ArtifactStore(Path(root))
            with guarded_execution(guard):
                state['lost']=True
                with self.assertRaises(RuntimeError): store.ingest_bytes(b'evidence',filename='test')
                with self.assertRaises(RuntimeError): PostgresRegistry('test').put('x',{})
            ensure_execution_allowed()  # Context must reset after failure.
            self.assertEqual(list(Path(root).glob('sha256/*/metadata.json')),[])
    def test_due_poll_is_limited_in_sql_and_updates_are_guarded(self):
        registry=PostgresRegistry('products')
        conn=MagicMock(); cursor=conn.cursor.return_value.__enter__.return_value
        @contextmanager
        def connect(): yield conn
        registry._connect=connect
        cursor.fetchall.return_value=[]
        registry.due_pending(50000)
        sql,args=cursor.execute.call_args.args
        self.assertIn('LIMIT %s',sql); self.assertEqual(args[-1],1000)
        cursor.fetchone.return_value=None
        self.assertFalse(registry.compare_and_put('x',{'status':'pending'}, {'status':'published'}))
        self.assertIn('value=%s::jsonb RETURNING key',cursor.execute.call_args.args[0])
    def test_revocation_is_not_overwritten(self):
        store=InMemoryRegistry(); original={'status':'pending_catalog_registration'}
        store.put('x',original); store.put('x',{'status':'revoked'})
        self.assertFalse(store.compare_and_put('x',original,{'status':'published'}))
        self.assertEqual(store.get('x')['status'],'revoked')
    def test_lost_lease_cannot_complete_and_readiness_distinguishes_executor(self):
        tree=ast.parse(Path('backend/data_pipeline_service/execution.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute_claimed_job')
        lost=threading.Event(); completed=[]
        run={'run_id':'r','status':'running','worker_id':'w','attempt':1,'lease':{'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}}
        def handler(*a,**k): lost.set(); return {'status':'completed'}
        scope={'Any':object,'datetime':datetime,'timezone':timezone,'guarded_execution':guarded_execution,'ensure_execution_allowed':ensure_execution_allowed,'run_records':SimpleNamespace(get=lambda _:run,complete=lambda *a:completed.append(a)), 'runner':object(),'handler_registry':SimpleNamespace(get=lambda _:SimpleNamespace(execute=handler))}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'execution','exec'),scope)
        with self.assertRaises(RuntimeError): scope['execute_claimed_job']({'job_type':'test'}, {}, run, lease_lost=lost)
        self.assertEqual(completed,[])
        tree=ast.parse(Path('backend/data_pipeline_service/worker_status.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execution_readiness')
        scope={'Any':object,'os':os,'summary':lambda:{'worker_count':0}}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'readiness','exec'),scope)
        with patch.dict(os.environ,{'DEPO_PIPELINE_EXECUTION_MODE':'worker'}): self.assertEqual(scope['execution_readiness']()['status'],'not_ready')
        with patch.dict(os.environ,{'DEPO_PIPELINE_EXECUTION_MODE':'inline'}): self.assertEqual(scope['execution_readiness']()['status'],'ready')
    def test_outbox_reconciliation_does_not_overwrite_concurrent_revocation(self):
        store=InMemoryRegistry(); store.put('x',{'status':'pending_catalog_registration'})
        async def register(record): store.put('x',{'status':'revoked'}); return {'status':'published'}
        node=next(n for n in ast.parse(Path('backend/data_product_service/router.py').read_text()).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='reconcile_pending')
        scope={'store':store,'_register_catalog':register}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'outbox','exec'),scope)
        result=asyncio.run(scope['reconcile_pending']())
        self.assertEqual(result['published'],0)
        self.assertEqual(store.get('x')['status'],'revoked')

    def test_worker_is_decoupled_and_code_network_has_source_coverage(self):
        worker=Path('backend/data_pipeline_service/worker.py').read_text()
        self.assertNotIn('from .router import',worker)
        self.assertIn('lease_lost.set()',worker)
        source=Path('tools/code_graph_audit.py')
        tree=ast.parse(source.read_text())
        tree.body=[n for n in tree.body if not (isinstance(n,ast.Import) and any(a.name=='networkx' for a in n.names)) and not (isinstance(n,ast.If) and '__name__' in ast.unparse(n.test))]
        scope={'__file__':str(source.resolve()),'__name__':'coverage'}
        exec(compile(tree,str(source),'exec'),scope)
        names={scope['rel'](p) for p in scope['files']()}
        self.assertIn('frontend/buildReceipt.mjs',names)
        self.assertIn('infra/windows/start-depo-services.ps1',names)
        self.assertTrue(any(p.startswith('infra/postgres/migrations/') and p.endswith('.sql') for p in names))
        self.assertFalse(any('/dist/' in p for p in names))

if __name__=='__main__': main()
