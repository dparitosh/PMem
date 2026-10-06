"""Exercise actual runner functions with durable-store and upstream fixtures."""
import ast
import asyncio
import copy
import json
import logging
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch, AsyncMock
from uuid import uuid4

import httpx
from fastapi import HTTPException, Request
from backend.agentic_service.recovery import prepare_recovery, reconcile, fingerprint, execution_payload
from backend.agentic_service.input_contracts import validate, validate_operation, validate_bindings
from backend.agentic_service.mapping_validation import check_mapping
from backend.agentic_service.workflow_control import checkpoint, WorkflowCancelled


def functions(path, names, namespace):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    for node in nodes:
        node.decorator_list = []
    namespace['__package__'] = 'backend.agentic_service'
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, 'exec'), namespace)
    return namespace


class Store:
    def __init__(self): self.records = {}
    def get(self, key): return copy.deepcopy(self.records.get(key))
    def create(self, key, value):
        if key in self.records: raise FileExistsError(key)
        self.records[key] = copy.deepcopy(value)
    def put(self, key, value): self.records[key] = copy.deepcopy(value)
    def compare_and_put(self, key, expected, value):
        if self.records.get(key) != expected: return False
        self.records[key] = copy.deepcopy(value)
        return True


def runner():
    store, controls = Store(), Store()
    workflow = {'id': 'fixture', 'steps': [{'agent_id':'test', 'tool_id':'read'}, {'agent_id':'test','tool_id':'write'}]}
    def planned(payload):
        return {'steps': [{'requires_approval': True, 'tool': {'id':step['tool_id'], 'mutates':step['tool_id']=='write'}} for step in workflow['steps']]}
    async def io(callback, *args, **kw): return callback(*args, **kw)
    ns = {'Any':Any, 'Request':Request, 'HTTPException':HTTPException, 'asyncio':asyncio, 'os':os,
          'datetime':datetime,'timezone':timezone,'timedelta':timedelta,'uuid4':uuid4,'time':__import__('time'),
          'logger':logging.getLogger('runner-test'), 'workflow_store':store, 'workflow_controls':controls,
          'catalog':SimpleNamespace(item=lambda *args:workflow), 'workflow_plan':planned,
          'approval_identity':lambda *args,**kw:'actor','graph_read_identity':lambda *args:'actor',
          'sessions':SimpleNamespace(owner=lambda *args:'owner'), '_agent_io':io,
          'telemetry':SimpleNamespace(start=lambda **kw:({'run_id':'telemetry'},0)),
          '_finish_observation':lambda *a,**kw:None,'_tool_span':lambda *a,**kw:None,
          '_preflight_tools':AsyncMock(), 'workflow_checkpoint':checkpoint,'WorkflowCancelled':WorkflowCancelled,
          'tool_retry_allowed':lambda *args,**kw:False}
    functions('backend/agentic_service/router.py', {'_now','_lookup','_resolve_inputs','_persist_workflow','_execute_workflow'}, ns)
    return ns, store, controls, workflow


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_steps_are_not_replayed(self):
        ns, store, _, workflow = runner()
        calls = []
        async def dispatch(command, request):
            calls.append(command['tool_id'])
            if command['tool_id'] == 'write' and len(calls) == 2:
                raise HTTPException(503, 'uncertain write')
            return {'result': {'receipt':'verified'}}
        ns['_dispatch'] = dispatch
        request = SimpleNamespace(state=SimpleNamespace(request_id='fixture'))
        with self.assertRaises(HTTPException):
            await ns['_execute_workflow']({'workflow_id':'fixture', 'inputs':{}}, request)
        record = next(iter(store.records.values()))
        self.assertEqual(record['traces'][0]['tool_id'], 'read')
        self.assertTrue(record['reconciliation_required'])
        with self.assertRaisesRegex(ValueError, 'Reconcile'):
            prepare_recovery(record, record['workflow_definition'])
        resolved = reconcile(record, 'not_applied', 'Checked downstream receipt store: no write applied', 'supervisor')
        recovery = prepare_recovery(resolved, record['workflow_definition'])
        store.put(record['run_id'], recovery)
        result = await ns['_execute_workflow'](recovery['execution_payload'], request, recovery=recovery)
        self.assertEqual(calls, ['read','write','write'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['deadline_at'], record['deadline_at'])
        self.assertNotIn('execution_payload', result)

    async def test_verified_completed_write_is_skipped(self):
        ns, store, _, workflow = runner()
        record = self.record(workflow)
        record.update(reconciliation_required=True, pending_step={'sequence':2,'tool_id':'write','mutates':True,'attempt':1})
        record['traces'] = [{'sequence':1,'tool_id':'read','status':'completed','result':{}}]
        updated = reconcile(record,'completed','Graph receipt publication-123','supervisor',{'publication_id':'123'})
        recovery = prepare_recovery(updated,workflow)
        store.put(record['run_id'],recovery)
        ns['_dispatch'] = AsyncMock()
        result = await ns['_execute_workflow'](recovery['execution_payload'],SimpleNamespace(state=SimpleNamespace(request_id='x')),recovery=recovery)
        ns['_dispatch'].assert_not_awaited()
        self.assertEqual(result['status'],'completed')

    def record(self, workflow):
        return {'run_id':'run-fixture', 'workflow_id':'fixture','status':'failed','execution_id':'old','traces':[],
                'deadline_at':(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat(),
                'started_at':datetime.now(timezone.utc).isoformat(),'updated_at':datetime.now(timezone.utc).isoformat(),
                'workflow_digest':fingerprint(workflow),'execution_payload':{'workflow_id':'fixture','inputs':{}}}

    async def test_deadline_and_definition_drift_block_recovery(self):
        _, _, _, workflow = runner()
        record = self.record(workflow)
        with self.assertRaisesRegex(ValueError, 'changed'):
            prepare_recovery(record, {'id':'changed'})
        record['deadline_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, 'expired'):
            prepare_recovery(record, workflow)

    async def test_stale_executor_is_fenced(self):
        ns, store, _, workflow = runner()
        record = self.record(workflow)
        store.put(record['run_id'], {**record,'execution_id':'replacement'})
        with self.assertRaises(HTTPException): await ns['_persist_workflow'](record)
        self.assertEqual(store.get(record['run_id'])['execution_id'],'replacement')

    async def test_failed_receipt_persistence_retains_uncertain_write(self):
        ns, store, _, _ = runner()
        original = store.compare_and_put
        failed = False
        def commit(key, expected, value):
            nonlocal failed
            if not failed and any(row.get('tool_id') == 'write' and row['status'] == 'completed' for row in value['traces']):
                failed = True
                raise OSError('Database connection interrupted after write')
            return original(key,expected,value)
        store.compare_and_put = commit
        ns['_dispatch'] = AsyncMock(return_value={'result': {'receipt':'applied'}})
        with self.assertRaises(HTTPException):
            await ns['_execute_workflow']({'workflow_id':'fixture'},SimpleNamespace(state=SimpleNamespace(request_id='x')))
        retained=next(iter(store.records.values()))
        self.assertTrue(retained['reconciliation_required'])
        self.assertEqual(retained['pending_step']['tool_id'],'write')
        self.assertEqual([row['tool_id'] for row in retained['traces'] if row['status']=='completed'],['read'])

    async def test_pause_then_cancel_before_next_tool(self):
        store=Store();store.put('run',{'action':'pause'})
        task=asyncio.create_task(checkpoint(store,'run'))
        await asyncio.sleep(0.02)
        self.assertFalse(task.done())
        store.put('run',{'action':'cancel'})
        with self.assertRaises(WorkflowCancelled): await task

    def test_persisted_payload_omits_credentials(self):
        result=execution_payload({'workflow_id':'x','approval_token':'secret','inputs':{'nested':{'api_key':'secret','field':1}}})
        self.assertNotIn('secret',json.dumps(result))

    def test_running_mutation_requires_verified_stopped_executor(self):
        _,_,_,workflow=runner()
        record=self.record(workflow)
        record.update(status='running', updated_at=(datetime.now(timezone.utc)-timedelta(seconds=90)).isoformat(),
                      pending_step={'sequence':1,'tool_id':'write','mutates':True,'attempt':1})
        with self.assertRaisesRegex(ValueError,'stopped'):
            reconcile(record,'not_applied','Checked receipt store','supervisor')
        updated=reconcile(record,'not_applied','Checked receipt store and stopped process','supervisor',executor_stopped=True)
        self.assertNotEqual(updated['execution_id'],record['execution_id'])


class ContractTests(unittest.TestCase):
    def test_future_references_and_unbounded_nesting_are_rejected(self):
        validate_bindings({'nested':['$steps.1.result.id']},1)
        for value in ('$steps.2.result.id','$steps.0.result.id','$steps.1.invalid'):
            with self.assertRaises(ValueError): validate_bindings(value,1)

    def test_schema_types_references_and_deferred_inputs(self):
        document={'components':{'schemas':{'Body':{'type':'object','required':['count'], 'properties':{'count':{'type':'integer','minimum':1}},'additionalProperties':False}}}}
        schema={'$ref':'#/components/schemas/Body'}
        for invalid in ({},{'count':'one'},{'count':0},{'count':True},{'count':1,'unknown':1}):
            with self.assertRaises(ValueError): validate(invalid,schema,document)
        validate({'count':'$steps.1.result.count'},schema,document,deferred=True)
        with self.assertRaises(ValueError):validate({'count':'$steps.1.result.count'},schema,document)
        validate({'count':2},schema,document)

    def test_later_step_invalid_input_is_detected_before_dispatch(self):
        doc={'paths':{'/api/v1/write':{'post':{'requestBody':{'content':{'application/json':{'schema':{'type':'object','required':['name'],'properties':{'name':{'type':'string','minLength':1}}}}}}}}}}
        with self.assertRaisesRegex(ValueError,'name'):
            validate_operation(doc,{'id':'write','path':'/write','method':'POST','mutates':True},{})

    def test_mapping_checks_detect_conflicts_and_missing_evidence(self):
        term={'kind':'DatatypeProperty','ranges':['urn:string'],'domains':['urn:Product']}
        checks=check_mapping({'datatype_iri':'urn:integer','domain_iri':'urn:Product','range_iri':'urn:string','ontology_iri':'urn:other'},term,{'ontology_iris':['urn:ontology']},True)
        self.assertEqual(checks['datatype_compatibility'],'failed')
        self.assertEqual(checks['domain_range_compatibility'],'passed')
        self.assertEqual(checks['scope_check'],'failed')
        self.assertEqual(checks['duplicate_check'],'failed')
        self.assertEqual(check_mapping('name',term,{},False)['domain_range_compatibility'],'not_supplied')


class PreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_input_schema_definitions_and_mutation_hints(self):
        from backend.agentic_service import mcp_transport
        tool={'id':'mcp.read','transport':'mcp','server_id':'fixture','name':'read_terms','mutates':False}
        schema={'type':'object','properties':{'count':{'$ref':'#/$defs/Count'}},
                '$defs':{'Count':{'type':'integer','minimum':1}}}
        native={'name':'read_terms','inputSchema':schema,'annotations':{'readOnlyHint':True}}
        ns={'Any':Any,'Request':Request,'httpx':httpx,'catalog':SimpleNamespace(item=lambda *args:{}),
            'plan':lambda command:{'tool':tool}}
        functions('backend/agentic_service/router.py',{'_preflight_tools'},ns)
        with patch.object(mcp_transport,'invoke',AsyncMock(return_value={'tools':[native]})):
            await ns['_preflight_tools']([{'inputs':{'count':1}}],SimpleNamespace())
            with self.assertRaises(ValueError): await ns['_preflight_tools']([{'inputs':{'count':0}}],SimpleNamespace())
            native['annotations']['readOnlyHint']=False
            with self.assertRaisesRegex(ValueError,'classification'):
                await ns['_preflight_tools']([{'inputs':{'count':1}}],SimpleNamespace())

    async def test_invalid_second_step_never_dispatches_first_step(self):
        ns,store,_,_=runner()
        from backend.agentic_service.response_limits import read_bounded_response
        tool={'id':'write','service':'fixture','path':'/write','method':'POST','transport':'openapi','mutates':True}
        document={'paths':{'/api/v1/write':{'post':{'requestBody':{'content':{'application/json':{
            'schema':{'type':'object','required':['name'],'properties':{'name':{'type':'string'}}}}}}}}}}
        ns.update(httpx=httpx,read_bounded_response=read_bounded_response,
                  plan=lambda command:{'tool':tool},_base=lambda service:'http://fixture/api/v1',
                  downstream_headers=lambda *args,**kwargs:{})
        functions('backend/agentic_service/router.py',{'_bounded_tool_request','_preflight_tools'},ns)
        ns['_dispatch']=AsyncMock()
        real_client=httpx.AsyncClient
        with patch.object(httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=document)),**kw)):
            with self.assertRaises(HTTPException) as caught:
                await ns['_execute_workflow']({'workflow_id':'fixture','step_inputs':[{'name':'valid'},{}]},SimpleNamespace(state=SimpleNamespace(request_id='x')))
        self.assertEqual(caught.exception.status_code,422)
        ns['_dispatch'].assert_not_awaited()
        self.assertFalse(store.records)


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_lifecycle_call_and_environment_isolation(self):
        from backend.agentic_service.mcp_transport import invoke
        script='''import sys,json,os
for line in sys.stdin:
    message=json.loads(line)
    if 'id' not in message: continue
    method=message['method']
    result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}}} if method=='initialize' else {'content':[{'type':'text','text':'result'}], 'secret_leaked':'OLLAMA_API_KEY' in os.environ}
    print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':result}),flush=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'server.py';path.write_text(script)
            with patch.dict(os.environ,{'OLLAMA_API_KEY':'must-not-leak'}):
                result=await invoke({'transport':'stdio','command':sys.executable,'args':[str(path)],'environment':[]},'tools/call',{'name':'read','arguments':{}})
            self.assertFalse(result['secret_leaked'])
            self.assertEqual(result['content'][0]['text'],'result')

    async def test_hung_server_is_terminated_at_deadline(self):
        from backend.agentic_service.mcp_transport import invoke
        with patch.dict(os.environ,{'AGENTIC_TOOL_TIMEOUT_SECONDS':'0.2'}):
            with self.assertRaises(TimeoutError):
                await invoke({'transport':'stdio','command':sys.executable,'args':['-c','import time; time.sleep(30)']},'tools/list')


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_sse_route_sends_status_before_generation_and_final_evidence(self):
        from fastapi.responses import StreamingResponse
        from backend.agentic_service.chat_request import ChatRequest
        async def io(callback,*args,**kwargs):return callback(*args,**kwargs)
        async def generate(payload,request,on_token):
            await on_token('first ')
            await asyncio.sleep(0)
            await on_token('second')
            return {'response':'first second','evidence':[],'sources':[],'answerable':True,'run_id':'fixture'}
        ns={'Any':Any,'Request':Request,'ChatRequest':ChatRequest,'StreamingResponse':StreamingResponse,
            'asyncio':asyncio,'json':json,'graph_read_identity':lambda request:'actor','_agent_io':io,
            'sessions':SimpleNamespace(open_session=lambda *args:{'session_id':'session','expires_at':'2099-01-01T00:00:00+00:00'}),
            '_companion_chat':generate}
        functions('backend/agentic_service/router.py',{'companion_stream'},ns)
        result=await ns['companion_stream'](ChatRequest(message='question'),SimpleNamespace())
        events=[]
        async for item in result.body_iterator:events.append(json.loads(item[6:].strip()))
        self.assertIn('status',events[0])
        self.assertEqual(events[1],{'token':'first '})
        self.assertEqual(events[2],{'token':'second'})
        self.assertEqual(events[-2]['response'],'first second')
        self.assertTrue(events[-1]['done'])

    async def test_oversized_ndjson_frame_is_rejected_before_parsing(self):
        from backend.agentic_service.local_llm import _stream_frames
        class Response:
            async def aiter_bytes(self):
                yield b'x'*65537
        with self.assertRaises(ValueError):
            async for _ in _stream_frames(Response()):pass

    async def test_ollama_chunks_arrive_before_stream_completion(self):
        from backend.agentic_service import local_llm
        chunks=[]
        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{"message":{"content":"first "},"done":false}\n'
                await asyncio.sleep(0)
                self.assert_streamed()
                yield b'{"message":{"content":"second"},"done":true}\n'
            def assert_streamed(self):
                if chunks != ['first ']: raise AssertionError('First token was buffered')
        real_client=httpx.AsyncClient
        transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Body()))
        async def emit(token):chunks.append(token)
        with patch.dict(os.environ,{'USE_LLM':'ollama','OLLAMA_API_URL':'http://fixture/api/chat','OLLAMA_BASE_URL':''}), patch.object(local_llm.httpx,'AsyncClient',lambda **kw:real_client(transport=transport,**kw)):
            result=await local_llm.summarize('question',[{'id':'evidence'}],on_token=emit)
        self.assertEqual(result,'first second')

    async def test_agent_prompt_and_allowlist_are_enforced(self):
        from backend.agentic_service import local_llm
        sent=[]
        def handler(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200,json={'message':{'content':json.dumps({'tool_id':'forbidden','inputs':{}})}})
        real_client=httpx.AsyncClient
        with patch.dict(os.environ,{'USE_LLM':'ollama','OLLAMA_API_URL':'http://fixture/api/chat','OLLAMA_BASE_URL':'','OLLAMA_CHAT_API_URL':''}),patch.object(local_llm.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw)):
            with self.assertRaises(ValueError):await local_llm.suggest_tool({'system_prompt':'Inspect only RDF'},[{'id':'read'}],'Inspect it')
        self.assertIn('Inspect only RDF',sent[0]['messages'][0]['content'])


if __name__ == '__main__': unittest.main()
