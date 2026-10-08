import ast
import asyncio
import copy
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock
from backend.agentic_service.workflow_receipts import compensation_plan


class HttpError(Exception):
    def __init__(self,status_code,detail): self.status_code,self.detail=status_code,detail


class Store:
    def __init__(self,record): self.record=copy.deepcopy(record)
    def get(self,key): return copy.deepcopy(self.record)
    def put(self,key,record): self.record=copy.deepcopy(record); return record
    def compare_and_put(self,key,expected,record):
        if self.record != expected: return False
        self.put(key,record); return True
    @contextmanager
    def advisory_lock(self,key): yield True


def actual_function(path,name,scope):
    tree=ast.parse(Path(path).read_text(encoding='utf-8'))
    node=next(item for item in tree.body if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)) and item.name==name)
    node.decorator_list=[]
    scope.update(Any=object,Request=object,HTTPException=HttpError,__package__='backend.agentic_service')
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual service boundary>','exec'),scope)
    return scope[name]


class CompensationRoutes(unittest.TestCase):
    def test_revocation_retry_is_idempotent_and_cannot_claim_another_revocation(self):
        store=Store({'product_id':'quality','version':'1.0.0','lifecycle_state':'published'})
        remote=AsyncMock(side_effect=lambda record:record)
        revoke=actual_function('backend/data_product_service/router.py','revoke',{
            'store':store,'approval_identity':lambda *args,**kwargs:'steward','_now':lambda:'timestamp',
            '_register_catalog':remote,'_public_product':lambda record:record})
        payload={'idempotency_key':'compensation-1','reason':'Withdraw evidence'}
        first=asyncio.run(revoke('quality:1.0.0',payload,object()))
        second=asyncio.run(revoke('quality:1.0.0',payload,object()))
        self.assertEqual(first,second)
        self.assertEqual(remote.await_count,1)
        with self.assertRaises(HttpError): asyncio.run(revoke('quality:1.0.0',{'idempotency_key':'other'},object()))

    def test_compensation_persists_intent_and_only_retries_the_same_operation(self):
        store=Store({'status':'failed','traces':[{'sequence':1,'status':'completed','tool_id':'data.product.publish','result':{'product_id':'quality','version':'1.0.0'}}]})
        async def io(callback,*args,**kwargs): return callback(*args,**kwargs)
        dispatch=AsyncMock(return_value={'result':{'lifecycle_state':'revoked'}})
        operation=actual_function('backend/agentic_service/router.py','compensate_workflow',{
            'workflow_store':store,'approval_identity':lambda *args,**kwargs:'supervisor','_agent_io':io,
            '_dispatch':dispatch,'_now':lambda:'timestamp'})
        payload={'sequence':1,'reason':'Withdraw evidence','approved_by':'supervisor','approval_token':'fixture'}
        first=asyncio.run(operation('run-1',payload,object()))
        second=asyncio.run(operation('run-1',payload,object()))
        self.assertEqual(first,second)
        self.assertEqual(dispatch.await_count,1)
        self.assertEqual(store.record['compensations']['1']['approved_actor'],'supervisor')
        self.assertEqual(dispatch.call_args.args[0]['inputs']['idempotency_key'],'compensate:run-1:1')

    def test_failed_compensation_retains_retry_identity_without_replaying_original_publish(self):
        store=Store({'status':'failed','traces':[{'sequence':1,'status':'completed','tool_id':'data.product.publish','result':{'product_id':'quality','version':'1.0.0'}}]})
        async def io(callback,*args,**kwargs): return callback(*args,**kwargs)
        dispatch=AsyncMock(side_effect=HttpError(503,'Response lost'))
        operation=actual_function('backend/agentic_service/router.py','compensate_workflow',{
            'workflow_store':store,'approval_identity':lambda *args,**kwargs:'supervisor','_agent_io':io,
            '_dispatch':dispatch,'_now':lambda:'timestamp'})
        with self.assertRaises(HttpError): asyncio.run(operation('run-1',{'sequence':1,'reason':'Withdraw evidence'},object()))
        self.assertEqual(store.record['compensations']['1']['status'],'pending')
        self.assertEqual(dispatch.call_args.args[0]['tool_id'],'data.product.revoke')

    def test_unsupported_graph_writes_are_visible_instead_of_deleted(self):
        result=compensation_plan({'status':'failed','traces':[{'sequence':1,'status':'completed','tool_id':'graph.publish','result':{}}],
                                  'workflow_definition':{'steps':[{'tool':{'mutates':True}}]}})
        self.assertEqual(result['actions'],[])
        self.assertEqual(result['unsupported'][0]['sequence'],1)
