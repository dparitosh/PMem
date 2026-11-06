import ast
import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import patch


class HttpError(Exception):
    def __init__(self, status): self.status_code = status


def extract(name, scope):
    tree = ast.parse(Path('backend/agentic_service/router.py').read_text())
    node = next(node for node in tree.body if getattr(node,'name','') == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<automation-audit>','exec'),scope)
    return scope[name]


class AutomationAuditFixTests(unittest.IsolatedAsyncioTestCase):
    def test_reader_owns_workflow_independently_of_approval_actor(self):
        fn = extract('_workflow_owner',{'graph_read_identity':lambda request:'reader',
            'HTTPException':HttpError,'sessions':SimpleNamespace(owner=lambda request,actor:actor)})
        self.assertEqual(fn(object(),'approval-actor'),'reader')

    def test_authority_outage_is_not_treated_as_missing_reader_permission(self):
        def unavailable(request): raise HttpError(503)
        fn = extract('_workflow_owner',{'graph_read_identity':unavailable,
            'HTTPException':HttpError,'sessions':SimpleNamespace(owner=lambda request,actor:actor)})
        with self.assertRaises(HttpError): fn(object(),'approval-actor')

    async def test_acceptance_returns_before_tool_finishes_and_browser_cannot_cancel_workflow(self):
        active = set()
        fn = extract('_keep_workflow_running',{'asyncio':asyncio,'_active_workflow_tasks':active,'logger':logging.getLogger(__name__)})
        accepted = asyncio.get_running_loop().create_future()
        release = asyncio.Event()
        writes = []
        async def operation():
            accepted.set_result({'run_id':'retained','status':'running'})
            await release.wait()
            writes.append('completed')
            return {'status':'completed'}
        result = await fn(operation(),accepted)
        self.assertEqual(result['run_id'],'retained')
        self.assertEqual(writes,[])
        self.assertEqual(len(active),1)
        release.set()
        await asyncio.gather(*active)
        self.assertEqual(writes,['completed'])

    async def test_pre_acceptance_failure_is_returned_to_caller(self):
        fn = extract('_keep_workflow_running',{'asyncio':asyncio,'_active_workflow_tasks':set(),'logger':logging.getLogger(__name__)})
        accepted = asyncio.get_running_loop().create_future()
        async def fail(): raise ValueError('preflight failed')
        with self.assertRaises(ValueError): await fn(fail(),accepted)
        self.assertTrue(accepted.cancelled())

    async def test_merge_reconciliation_only_reads_verified_receipt(self):
        from backend.agentic_service.workflow_receipts import lookup
        fastapi = ModuleType('fastapi'); fastapi.HTTPException = HttpError
        routes = ModuleType('backend.agentic_service.router'); routes._base = lambda service:'https://test/api/v1'
        transport = ModuleType('backend.agentic_service.transport_auth'); transport.downstream_headers = lambda *args,**kwargs:{}
        httpx = ModuleType('httpx')
        class Client:
            def __init__(self,**kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
        httpx.AsyncClient = Client
        calls=[]
        async def request(client,method,url,**kwargs):
            calls.append((method,url))
            return SimpleNamespace(json=lambda:{'status':'merged','preview_id':'saved','ontology':{'ontology_id':'draft'}})
        routes._bounded_tool_request=request
        modules={item.__name__:item for item in (fastapi,routes,transport,httpx)}
        record={'pending_step':{'tool_id':'ontology.merge.apply_automatic','inputs':{'preview_id':'saved'}}}
        with patch.dict(sys.modules,modules): result=await lookup(record,object())
        self.assertEqual(result['ontology']['ontology_id'],'draft')
        self.assertEqual(calls,[('GET','https://test/api/v1/ontologies/merges/saved/receipt')])
