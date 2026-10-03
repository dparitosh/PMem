import ast
import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock
from tempfile import TemporaryDirectory
from backend.mesh_store import InMemoryRegistry, PostgresRegistry

ROOT = Path(__file__).resolve().parents[2]
def load(relative, names, scope):
    nodes = [n for n in ast.parse((ROOT/relative).read_text(encoding='utf-8-sig')).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for node in nodes: node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), relative, 'exec'), scope)
    return scope

class WorkflowTests(TestCase):
    def test_stale_lifecycle_update_preserves_disable(self):
        store = InMemoryRegistry()
        original = {'job_id':'example', 'version':'1.0.0', 'enabled':True, 'lifecycle_state':'draft'}
        store.put('example:1.0.0', original)
        def get(key):
            snapshot = dict(store.values[key])
            store.values[key] = {**snapshot, 'enabled':False, 'lifecycle_state':'disabled'}
            return snapshot
        store.get = get
        scope = load('backend/data_pipeline_service/job_definitions.py', {'get','key','approve','_update'}, {'Any':object,'store':store,'now':lambda:'now'})
        with self.assertRaises(ValueError): scope['approve']('example','1.0.0','steward')
        self.assertFalse(store.values['example:1.0.0']['enabled'])

    def test_inline_output_failure_is_terminal(self):
        class Runs:
            def start(self,*a,**kw): self.state='running'; return {'run_id':'example'}
            def failed(self,*a): self.state='failed'
            def complete(self,*a): raise OSError('storage unavailable')
        runs=Runs()
        handler=SimpleNamespace(execute=lambda *a,**kw:{'status':'completed'})
        scope=load('backend/data_pipeline_service/router.py',{'execute_configured_job'}, {'Any':object,'run_records':runs,'runner':None,'handler_registry':SimpleNamespace(get=lambda _:handler)})
        with self.assertRaises(OSError):scope['execute_configured_job']({'job_type':'example'}, {}, 'correlation')
        self.assertEqual(runs.state,'failed')

    def test_heartbeat_rejects_old_attempt_and_expired_lease(self):
        store=InMemoryRegistry()
        now=datetime.now(timezone.utc)
        record={'status':'running','worker_id':'same','attempt':2,'lease':{'expires_at':(now+timedelta(seconds=60)).isoformat()}}
        store.put('run',record)
        new={'expires_at':(now+timedelta(seconds=120)).isoformat()}
        self.assertIsNone(store.heartbeat(key='run',worker_id='same',attempt=1,lease=new))
        self.assertIsNotNone(store.heartbeat(key='run',worker_id='same',attempt=2,lease=new))
        store.put('run',{**record,'lease':{'expires_at':(now-timedelta(seconds=1)).isoformat()}})
        self.assertIsNone(store.heartbeat(key='run',worker_id='same',attempt=2,lease=new))

    def test_sql_heartbeat_and_latest_job_filter(self):
        registry=PostgresRegistry('data_job_runs'); connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
        @contextmanager
        def connect():yield connection
        registry._connect=connect
        registry.heartbeat(key='run',worker_id='worker',attempt=2,lease={})
        sql,params=cursor.execute.call_args.args
        self.assertIn("expires_at')::timestamptz > now()",sql)
        self.assertIn("value->>'attempt'",sql);self.assertEqual(params[-1],2)
        registry.latest_job_run('example','1.0.0')
        sql,params=cursor.execute.call_args.args
        self.assertIn("value->>'job_id'=%s",sql);self.assertIn('LIMIT 1',sql)
        self.assertEqual(params,('data_job_runs','example','1.0.0'))

    def test_publication_without_checkpoint_is_idempotent(self):
        store=InMemoryRegistry();receipt={'status':'published','ontology_id':'target'}
        record={'run_id':'run','output_manifest':{'checkpoint_state':'not_applicable','publication':receipt}}
        scope=load('backend/data_pipeline_service/run_records.py',{'publication_succeeded'},{'Any':object,'store':store,'_now':lambda:'now','_digest':lambda v:'digest'})
        self.assertEqual(scope['publication_succeeded'](record,receipt),record)
        with self.assertRaises(ValueError):scope['publication_succeeded'](record,{**receipt,'ontology_id':'other'})

    def test_publication_route_reuses_receipt_and_rejects_destination_change(self):
        class HttpError(Exception):
            def __init__(self, status_code, detail):self.status_code=status_code;self.detail=detail
        with TemporaryDirectory() as root:
            artifact=Path(root)/'accepted.json';artifact.write_text(json.dumps({'standard':'qif'}))
            store=InMemoryRegistry();receipt={'status':'published','ontology_id':'target'}
            record={'run_id':'run','status':'completed','job_type':'normalize-ceim','output_manifest':{'partition_artifacts':{'accepted':'artifact'},'publication':receipt}}
            store.put('run',record)
            runs=SimpleNamespace(store=store,get=store.get,_digest=lambda v:'digest')
            artifacts=SimpleNamespace(resolve=lambda _:({'kind':'accepted-semantic-partition'},artifact))
            scope=load('backend/data_pipeline_service/router.py',{'publish_job_run'}, {'Any':object,'Request':object,'approval_identity':lambda *a,**kw:'steward','HTTPException':HttpError,'run_records':runs,'ArtifactStore':lambda:artifacts,'json':json,'httpx':SimpleNamespace(HTTPError=ConnectionError)})
            request=SimpleNamespace(headers={})
            result=asyncio.run(scope['publish_job_run']('run',{'ontology_id':'target'},request))
            self.assertEqual(result,record)
            with self.assertRaises(HttpError) as failure:asyncio.run(scope['publish_job_run']('run',{'ontology_id':'other'},request))
            self.assertEqual(failure.exception.status_code,409)
            self.assertEqual(store.get('run')['output_manifest']['publication'],receipt)
            store.put('run',{**record,'output_manifest':{'partition_artifacts':{'accepted':'artifact'},'publication_intent':{'ontology_id':'first'}}})
            with self.assertRaises(HttpError) as failure:asyncio.run(scope['publish_job_run']('run',{'ontology_id':'other'},request))
            self.assertEqual(failure.exception.status_code,409)

    def test_ingestion_routes_and_bridge_use_supported_contracts(self):
        tree=ast.parse((ROOT/'backend/ingestion_service/tracked_import.py').read_text())
        routes={d.args[0].value for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for d in n.decorator_list if isinstance(d,ast.Call)}
        self.assertEqual(routes,{'/upload','/status/{task_id}','/preview/{task_id}','/pre-commit/{task_id}','/commit/{task_id}','/cancel/{task_id}'})
        app=(ROOT/'backend/ingestion_service/app.py').read_text();self.assertIn('app.include_router(tracked_import_router',app)
        ui=(ROOT/'frontend/src/Components/DataImportPipeline.js').read_text()
        self.assertIn('<SemanticBridgeJobs ',ui);self.assertIn('apply_links: false',ui);self.assertNotIn('workflowApplyLinks',ui)

    def test_cadence_is_below_stale_threshold_and_scheduler_is_job_scoped(self):
        worker=(ROOT/'backend/data_pipeline_service/worker.py').read_text()
        self.assertIn('stale_seconds / 3',worker)
        for lease in (30,300,3600):
            for stale in (30,60,3600):self.assertLess(min(max(1,lease//3),stale/3),stale)
        scheduler=(ROOT/'backend/data_pipeline_service/scheduler.py').read_text()
        self.assertIn('store.latest_job_run',scheduler);self.assertNotIn('list_runs(limit=1000)',scheduler)

if __name__=='__main__': main()
