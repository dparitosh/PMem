import asyncio
import copy
import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from backend.agentic_service.workflow_control import checkpoint, workflow_snapshot, WorkflowCancelled


class Store:
    def __init__(self, control): self.control = control
    def get(self, key): return copy.deepcopy(self.control)
    def compare_and_put(self, key, expected, value):
        if expected != self.control: return False
        self.control = value
        return True


class WorkflowControlStates(unittest.TestCase):
    def record(self, **updates):
        now = datetime.now(timezone.utc)
        return {'run_id':'run', 'status':'running', 'updated_at':(now-timedelta(seconds=120)).isoformat(),
                'deadline_at':(now+timedelta(seconds=300)).isoformat(), 'traces':[], **updates}

    def test_heartbeat_blocks_reconciliation_despite_old_step_timestamp(self):
        record = self.record(pending_step={'mutates':True})
        value = workflow_snapshot(record, heartbeat={'updated_at':datetime.now(timezone.utc).isoformat()})
        self.assertTrue(value['executor_active'])
        self.assertFalse(value['reconcile_allowed'])

    def test_acknowledged_pause_and_irreversible_cancel_have_distinct_controls(self):
        heartbeat = {'updated_at':datetime.now(timezone.utc).isoformat()}
        record = self.record()
        waiting = workflow_snapshot(record, {'action':'pause'}, heartbeat)
        self.assertEqual(waiting['execution_state'], 'pause_requested')
        paused = workflow_snapshot(record, {'action':'pause','effective_action':'pause','acknowledged_at':'timestamp'}, heartbeat)
        self.assertEqual(paused['execution_state'],'paused')
        self.assertEqual(paused['allowed_actions'],['resume','cancel'])
        cancelled = workflow_snapshot(record, {'action':'cancel'}, heartbeat)
        self.assertEqual(cancelled['allowed_actions'],[])

    def test_expired_read_does_not_invent_an_uncertain_write(self):
        value = workflow_snapshot(self.record(deadline_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()))
        self.assertEqual(value['status'],'interrupted')
        self.assertFalse(value['reconciliation_required'])
        self.assertFalse(value['recover_allowed'])

    def test_cancel_is_acknowledged_before_stopping_at_boundary(self):
        store = Store({'action':'cancel'})
        with self.assertRaises(WorkflowCancelled): asyncio.run(checkpoint(store,'run'))
        self.assertEqual(store.control['effective_action'],'cancel')
        self.assertIn('acknowledged_at',store.control)

    def test_racing_cancel_cannot_be_overwritten_by_resume_ack(self):
        class RacingStore(Store):
            def compare_and_put(self, key, expected, value):
                if expected['action'] == 'resume':
                    self.control = {'action':'cancel'}
                    return False
                return super().compare_and_put(key,expected,value)
        store = RacingStore({'action':'resume'})
        with self.assertRaises(WorkflowCancelled): asyncio.run(checkpoint(store,'run'))
        self.assertEqual(store.control['action'],'cancel')

    def test_browser_cancellation_does_not_cancel_authorized_execution(self):
        tree = ast.parse(Path('backend/agentic_service/router.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name == '_keep_workflow_running')
        ns = {'asyncio':asyncio,'_active_workflow_tasks':set(),'logger':SimpleNamespace(warning=lambda *args:None)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual task supervisor>','exec'),ns)
        async def check():
            started, finish = asyncio.Event(), asyncio.Event()
            completed = []
            async def execute():
                started.set()
                await finish.wait()
                completed.append(True)
            caller = asyncio.create_task(ns['_keep_workflow_running'](execute()))
            await started.wait()
            caller.cancel()
            with self.assertRaises(asyncio.CancelledError): await caller
            self.assertEqual(len(ns['_active_workflow_tasks']),1)
            finish.set()
            await asyncio.gather(*ns['_active_workflow_tasks'])
            await asyncio.sleep(0)
            self.assertEqual(completed,[True])
            self.assertFalse(ns['_active_workflow_tasks'])
        asyncio.run(check())
