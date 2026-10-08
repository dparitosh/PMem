"""Regression checks for queue starvation and authoritative workflow state."""
import asyncio
import copy
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from backend.agentic_service.bridge_jobs import BridgeJobs, BridgeConflict
from backend.agentic_service.workflow_control import workflow_snapshot
from backend.agentic_service.workflow_receipts import lookup
from backend.mesh_store import InMemoryRegistry
from backend.tests import test_durable_workflow_worker as durable_tests
from backend.tests.test_workflow_compensation_routes import actual_function, HttpError


class WorkflowAuditRegressions(unittest.TestCase):
    def test_expired_recoverable_candidates_leave_queue_but_uncertain_writes_remain(self):
        case = durable_tests.DurableWorkerTests()
        with patch.dict(os.environ, {'GRAPH_READ_TOKEN': 'fixture-read'}, clear=True):
            for status in ('queued', 'interrupted', 'running'):
                with self.subTest(status=status):
                    record, store, routes, modules = case.fixture(status=status,
                        deadline_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
                    case.run_candidate(record, modules)
                    self.assertEqual(store.record['status'], 'timed_out')
                    routes._execute_workflow.assert_not_awaited()
            record, store, routes, modules = case.fixture(status='running',
                deadline_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
                pending_step={'mutates': True})
            case.run_candidate(record, modules)
            self.assertEqual(store.record, record)
            routes._execute_workflow.assert_not_awaited()

    def test_stale_write_reports_interruption_and_reconciliation_without_claiming_executor_stopped(self):
        case = durable_tests.DurableWorkerTests()
        record, _, _, _ = case.fixture(status='running', pending_step={'mutates': True})
        state = workflow_snapshot(record)
        self.assertEqual(state['status'], 'interrupted')
        self.assertTrue(state['reconciliation_required'])
        self.assertTrue(state['reconcile_allowed'])
        self.assertTrue(state['executor_stop_verification_required'])
        self.assertFalse(state['executor_active'])
        self.assertFalse(state['recover_allowed'])
        self.assertEqual(state['allowed_actions'], [])
        live = workflow_snapshot(record, heartbeat={'updated_at': datetime.now(timezone.utc).isoformat()})
        self.assertEqual(live['status'], 'running')
        self.assertFalse(live['reconcile_allowed'])

    def test_bridge_lookup_persists_verified_receipt_without_publishing_again(self):
        store = InMemoryRegistry()
        job = {'job_id': 'publication', 'status': 'retryable', 'approved_ids': ['candidate'],
               'request_digest': 'retained-digest', 'error': 'Response lost'}
        store.put('preview', {'publication_job_id': 'publication'})
        store.put('publication', copy.deepcopy(job))
        receipt = {'publication_id': 'publication', 'request_digest': 'retained-digest'}
        graph = SimpleNamespace(receipt=lambda key: receipt,
            publish=lambda command: self.fail('Receipt reconciliation must not publish'))
        jobs = BridgeJobs(store=store, source=object(), graph=graph)
        bridge = ModuleType('backend.agentic_service.bridge_router'); bridge.jobs = jobs
        routes = ModuleType('backend.agentic_service.router')
        async def io(callback, *args): return callback(*args)
        routes._agent_io = io
        fastapi = ModuleType('fastapi'); fastapi.HTTPException = HttpError
        modules = {module.__name__: module for module in (bridge, routes, fastapi)}
        record = {'pending_step': {'tool_id': 'bridge.mapping.publish',
            'inputs': {'preview_id': 'preview', 'approved_candidate_ids': ['candidate']}}}
        with patch.dict(sys.modules, modules):
            result = asyncio.run(lookup(record, object()))
        self.assertEqual(result['status'], 'published')
        self.assertEqual(store.get('publication')['status'], 'published')
        self.assertNotIn('error', store.get('publication'))
        store.put('publication', copy.deepcopy(job))
        receipt['request_digest'] = 'different'
        with self.assertRaises(BridgeConflict): jobs.reconcile_receipt('publication', ['candidate'])
        self.assertEqual(store.get('publication'), job)
        with self.assertRaises(BridgeConflict): jobs.reconcile_receipt('publication', ['other'])

    def test_owner_history_is_filtered_before_limit_and_supervisor_sees_all(self):
        store = InMemoryRegistry()
        store.put('mine', {'run_id': 'mine', 'owner': 'reader-owner'})
        for index in range(120):
            store.put(str(index), {'run_id': str(index), 'owner': 'another-owner'})
        supervisor = False
        def authorize(*args, **kwargs):
            if not supervisor: raise HttpError(403, 'Reader only')
        auth = ModuleType('backend.depo_platform.authorization'); auth.service_write_identity = authorize
        operation = actual_function('backend/agentic_service/router.py', 'list_workflow_runs', {
            'workflow_store': store, 'sessions': SimpleNamespace(owner=lambda *args: 'reader-owner'),
            'graph_read_identity': lambda request: 'reader'})
        with patch.dict(sys.modules, {auth.__name__: auth}):
            result = operation(object(), limit=50)
            self.assertEqual([row['run_id'] for row in result['runs']], ['mine'])
            self.assertNotIn('owner', result['runs'][0])
            supervisor = True
            result = operation(object(), limit=50)
            self.assertEqual(len(result['runs']), 50)
            self.assertNotIn('mine', [row['run_id'] for row in result['runs']])
