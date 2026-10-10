import ast
import asyncio
import copy
import hashlib
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.depo_platform.network import bounded_timeout_seconds
from backend.agentic_service.workflow_control import execution_heartbeat, last_activity, checkpoint
from backend.agentic_service.recovery import prepare_recovery

class HTTPException(Exception):
    def __init__(self, status_code, detail): self.status_code=status_code

class TimingRegressions(unittest.TestCase):
    def test_invalid_timing_is_bounded(self):
        for value in ('oops','NaN','inf','-10','0'):
            with patch.dict(os.environ, {'TEST_TIMEOUT':value}):
                self.assertEqual(bounded_timeout_seconds('TEST_TIMEOUT',default=30),30)
        with patch.dict(os.environ, {'TEST_TIMEOUT':'99999'}):
            self.assertEqual(bounded_timeout_seconds('TEST_TIMEOUT',default=30),3600)

    def test_concurrent_session_updates_cannot_regress_activity(self):
        tree=ast.parse(Path('backend/agentic_service/sessions.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='open_session')
        lock=threading.Lock()
        current=datetime.now(timezone.utc)
        old=current-timedelta(seconds=10)
        class Store:
            value={'owner':'same','expires_at':(current+timedelta(hours=1)).isoformat(),'last_seen_at':old.isoformat()}
            @contextmanager
            def advisory_lock(self,key):
                with lock: yield True
            def get(self,key): return copy.deepcopy(self.value)
            def put(self,key,value): self.value=copy.deepcopy(value)
        store=Store()
        barrier=threading.Barrier(2)
        def request_time():
            index=barrier.wait()
            return old if index==0 else current
        ns={'store':store,'now':request_time,'owner':lambda *args:'same', 'uuid4':lambda:'new','HTTPException':HTTPException,'datetime':datetime,'timedelta':timedelta,'bounded_timeout_seconds':bounded_timeout_seconds}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<session>','exec'),ns)
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda _:ns['open_session'](None,'actor','session'),range(2)))
        self.assertEqual(store.value['last_seen_at'],current.isoformat())

    def test_fresh_heartbeat_blocks_recovery_of_long_tool_or_pause(self):
        now=datetime.now(timezone.utc)
        record={'status':'running','updated_at':(now-timedelta(seconds=120)).isoformat()}
        activity=last_activity(record,{'updated_at':now.isoformat()})
        with self.assertRaisesRegex(ValueError,'recent activity'):
            prepare_recovery(record,{},activity_at=activity)

    def test_heartbeat_continues_while_workflow_is_paused_and_deadline_still_applies(self):
        async def run():
            values={}
            class Heartbeats:
                def put(self,key,value):values[key]=value
            class Controls:
                def get(self,key):return {'action':'pause'}
                def compare_and_put(self,key,expected,value):return True
            with self.assertRaises(TimeoutError):
                async with asyncio.timeout(.1), execution_heartbeat(Heartbeats(),'run:execution'):
                    await checkpoint(Controls(),'run')
            self.assertIn('run:execution',values)
        asyncio.run(run())

    def test_pruning_checks_idle_and_absolute_expiry(self):
        tree=ast.parse(Path('backend/agentic_service/sessions.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='prune')
        calls=[]
        class DB:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def cursor(self):return self
            def execute(self,query,args):calls.append((query,args))
        ns={'store':SimpleNamespace(_connect=lambda:DB(),namespace='sessions'),'bounded_timeout_seconds':bounded_timeout_seconds}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<prune>','exec'),ns)
        ns['prune']()
        self.assertIn('last_seen_at',calls[0][0])
        self.assertEqual(len(calls), 2)
        self.assertIn('DELETE FROM depo_registry', calls[1][0])
        self.assertIn('expires_at', calls[1][0])
        self.assertEqual(calls[1][1], ('sessions',))
        self.assertEqual(calls[0][1],('sessions',1800))

if __name__=='__main__':unittest.main()
