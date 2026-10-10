import asyncio
import copy
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch
from backend.agentic_service.durable_workflows import credential_snapshot, transport_snapshot, clean_command, execute_candidate, enqueue, _worker_loop
from backend.agentic_service.recovery import fingerprint, prepare_recovery
from backend.agentic_service.workflow_receipts import compensation_plan, verify_product_receipt


class Store:
    def __init__(self, record): self.record = copy.deepcopy(record)
    def get(self, key): return copy.deepcopy(self.record)
    def compare_and_put(self,key,expected,value):
        if self.record != expected: return False
        self.record = copy.deepcopy(value)
        return True
    def create(self,key,value): self.record=copy.deepcopy(value); return value


class DurableWorkerTests(unittest.TestCase):
    def test_submission_retains_authorized_command_and_returns_a_pollable_identity(self):
        with patch.dict(os.environ,{'GRAPH_READ_TOKEN':'server-read','AGENTIC_APPROVAL_TOKEN':'server-supervisor'},clear=True):
            _,store,routes,modules=self.fixture()
            auth=modules['backend.depo_platform.authorization']
            auth.graph_read_identity=lambda request:'reader'
            auth.approval_identity=lambda *args,**kwargs:'supervisor'
            sessions=ModuleType('backend.agentic_service.sessions'); sessions.owner=lambda *args:'original-owner'
            fastapi=ModuleType('fastapi'); fastapi.HTTPException=type('HttpError',(Exception,),{'__init__':lambda self,*args:Exception.__init__(self,*args)})
            modules.update({sessions.__name__:sessions,fastapi.__name__:fastapi})
            routes._preflight_tools=AsyncMock()
            routes._workflow_owner=lambda *args:'original-owner'
            with patch.dict(sys.modules,modules):
                result=asyncio.run(enqueue({'workflow_id':'review','inputs':{'artifact':'retained'},'approval_token':'browser-secret'},object()))
            self.assertEqual(result['status'],'queued')
            self.assertEqual(store.record['owner'],'original-owner')
            self.assertEqual(store.record['execution_payload'],{'workflow_id':'review','inputs':{'artifact':'retained'}})
            self.assertNotIn('browser-secret',str(store.record))
            self.assertNotIn('server-read',str(store.record))
            routes._preflight_tools.assert_awaited_once()

    def fixture(self, **updates):
        workflow = {'id':'review','steps':[{'agent_id':'review','tool_id':'read'}]}
        steps = [{'requires_approval':False,'tool':{'id':'read','mutates':False}}]
        definition = {'workflow':workflow,'steps':steps}
        now = datetime.now(timezone.utc)
        record = {'run_id':'run-1','workflow_id':'review','status':'queued','execution_mode':'worker',
                  'owner':'original-owner','execution_id':'queued','execution_payload':{'workflow_id':'review'},
                  'workflow_definition':definition,'workflow_digest':fingerprint(definition),'approved_actor':'approved-reader',
                  'credential_fingerprints':credential_snapshot(),'transport_fingerprint':transport_snapshot(),'started_at':now.isoformat(),
                  'updated_at':(now-timedelta(seconds=120)).isoformat(),'deadline_at':(now+timedelta(seconds=300)).isoformat(),
                  'traces':[],**updates}
        store = Store(record)
        async def io(callback,*args,**kwargs): return callback(*args,**kwargs)
        routes = ModuleType('backend.agentic_service.router')
        routes.workflow_store=store
        routes.workflow_heartbeats=SimpleNamespace(get=lambda key:None)
        routes.catalog=SimpleNamespace(item=lambda *args:workflow)
        routes.workflow_plan=lambda payload:{'steps':steps}
        routes._agent_io=io
        routes._execute_workflow=AsyncMock()
        auth = ModuleType('backend.depo_platform.authorization'); auth.require_active_token=lambda name:None
        credentials = ModuleType('backend.depo_platform.credentials'); credentials.uses_postgres=lambda:False; credentials.verify_key=lambda *args:None
        requests = ModuleType('starlette.requests')
        requests.Request=lambda scope:SimpleNamespace(scope=scope,state=SimpleNamespace())
        modules = {routes.__name__:routes, auth.__name__:auth, credentials.__name__:credentials,requests.__name__:requests}
        return record,store,routes,modules

    def run_candidate(self, record, modules):
        with patch.dict(sys.modules,modules): asyncio.run(execute_candidate(record))

    def test_queued_job_is_claimed_and_runs_without_persisted_caller_keys(self):
        with patch.dict(os.environ,{'GRAPH_READ_TOKEN':'fixture-read','AGENTIC_APPROVAL_TOKEN':'fixture-supervisor'},clear=True):
            record,store,routes,modules=self.fixture()
            self.run_candidate(record,modules)
        routes._execute_workflow.assert_awaited_once()
        self.assertEqual(store.record['status'],'running')
        self.assertEqual(routes._execute_workflow.call_args.kwargs['recovery']['owner'],'original-owner')
        self.assertNotIn('fixture-read',str(record))
        self.assertNotIn('fixture-supervisor',str(record))

    def test_rotation_blocks_queued_execution(self):
        with patch.dict(os.environ,{'GRAPH_READ_TOKEN':'fixture-read'},clear=True):
            record,store,routes,modules=self.fixture()
            os.environ['GRAPH_READ_TOKEN']='rotated-read'
            self.run_candidate(record,modules)
        routes._execute_workflow.assert_not_awaited()
        self.assertEqual(store.record['error_type'],'WorkerAuthorizationChanged')

    def test_unrelated_rotation_does_not_block_scoped_read_grant(self):
        with patch.dict(os.environ, {'GRAPH_READ_TOKEN':'read', 'DATA_PRODUCT_APPROVAL_TOKEN':'old'}, clear=True):
            record,store,routes,modules=self.fixture(credential_fingerprints=credential_snapshot({'GRAPH_READ_TOKEN'}))
            os.environ['DATA_PRODUCT_APPROVAL_TOKEN']='new'
            self.run_candidate(record,modules)
        routes._execute_workflow.assert_awaited_once()

    def test_submission_scopes_read_grant(self):
        from backend.agentic_service.durable_workflows import workflow_credentials
        self.assertEqual(workflow_credentials([{'requires_approval':False, 'tool':{'id':'read','mutates':False}}]), {'GRAPH_READ_TOKEN'})

    def test_changed_service_destination_blocks_existing_grant(self):
        with patch.dict(os.environ,{'GRAPH_READ_TOKEN':'fixture-read','GRAPH_SERVICE_URL':'http://original'},clear=True):
            record,store,routes,modules=self.fixture()
            os.environ['GRAPH_SERVICE_URL']='http://different'
            self.run_candidate(record,modules)
        routes._execute_workflow.assert_not_awaited()
        self.assertEqual(store.record['error_type'],'WorkerAuthorizationChanged')

    def test_paused_execution_does_not_block_other_available_worker_slots(self):
        async def check():
            seen=[]
            async def execute(record):
                seen.append(record['run_id'])
                if record['run_id']=='paused': await asyncio.Event().wait()
            async def io(callback,*args): return callback(*args)
            routes=SimpleNamespace(_agent_io=io,workflow_store=SimpleNamespace(execution_candidates=lambda *args:[{'run_id':'paused'},{'run_id':'other'}]))
            real_sleep=asyncio.sleep
            async def tick(seconds):
                await real_sleep(0)
                if len(seen)==2: raise asyncio.CancelledError()
            with patch.dict(os.environ,{'AGENTIC_EXECUTION_MODE':'worker','AGENTIC_WORKER_CONCURRENCY':'2'},clear=True), patch('backend.agentic_service.durable_workflows.execute_candidate',execute), patch('backend.agentic_service.durable_workflows.asyncio.sleep',tick):
                with self.assertRaises(asyncio.CancelledError): await _worker_loop(routes,SimpleNamespace(getLogger=lambda *args:SimpleNamespace(warning=lambda *args:None)))
            self.assertEqual(seen,['paused','other'])
        asyncio.run(check())

    def test_stale_uncertain_mutation_is_never_replayed(self):
        with patch.dict(os.environ,{'GRAPH_READ_TOKEN':'fixture-read'},clear=True):
            record,store,routes,modules=self.fixture(status='running',pending_step={'mutates':True},reconciliation_required=True)
            self.run_candidate(record,modules)
        routes._execute_workflow.assert_not_awaited()

    def test_stale_read_only_execution_retains_original_deadline(self):
        with patch.dict(os.environ,{'GRAPH_READ_TOKEN':'fixture-read'},clear=True):
            record,store,routes,modules=self.fixture(status='running',pending_step={'mutates':False})
            self.run_candidate(record,modules)
        recovery=routes._execute_workflow.call_args.kwargs['recovery']
        self.assertEqual(recovery['deadline_at'],record['deadline_at'])

    def test_lost_claim_does_not_dispatch(self):
        with patch.dict(os.environ,{'GRAPH_READ_TOKEN':'fixture-read'},clear=True):
            record,store,routes,modules=self.fixture()
            store.record['execution_id']='other-worker'
            self.run_candidate(record,modules)
        routes._execute_workflow.assert_not_awaited()

    def test_queue_expiry_blocks_execution(self):
        with patch.dict(os.environ,{'GRAPH_READ_TOKEN':'fixture-read'},clear=True):
            record,store,routes,modules=self.fixture(deadline_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
            self.run_candidate(record,modules)
        routes._execute_workflow.assert_not_awaited()
        self.assertEqual(store.record['status'],'timed_out')

    def test_secret_inputs_are_rejected(self):
        with self.assertRaises(ValueError): clean_command({'workflow_id':'review','inputs':{'OLLAMA_API_KEY':'fixture'}})

    def test_receipt_must_match_identity_and_artifacts(self):
        inputs={'product_id':'quality','version':'1.0.0','idempotency_key':'run-1','artifacts':[{'artifact_id':'evidence'}]}
        receipt={**inputs,'publication_digest':'verified-digest'}
        self.assertEqual(verify_product_receipt(inputs,receipt),receipt)
        with self.assertRaises(ValueError): verify_product_receipt(inputs,{**receipt,'idempotency_key':'other-run'})
        with self.assertRaises(ValueError): verify_product_receipt(inputs,{**receipt,'artifacts':[{'artifact_id':'other'}]})

    def test_compensation_is_explicit_and_blocks_resuming_obsolete_outputs(self):
        record={'status':'failed','traces':[{'sequence':1,'tool_id':'data.product.publish','status':'completed','result':{'product_id':'quality','version':'1.0.0'}}]}
        value=compensation_plan(record)
        self.assertEqual(value['actions'][0]['product_version'],'quality:1.0.0')
        self.assertFalse(value['automatic_rollback'])
        with self.assertRaises(ValueError): compensation_plan({**record,'pending_step':{'mutates':True}})
        with self.assertRaisesRegex(ValueError,'compensated'): prepare_recovery({**record,'compensations':{'1':{'status':'completed'}}},{})
