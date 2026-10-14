import unittest
import ast
import asyncio
from pathlib import Path
from unittest.mock import patch
from backend.mesh_store import InMemoryRegistry
from backend.ontology_service.publication_jobs import PublicationJobs


class PublicationJobTests(unittest.TestCase):
    def setUp(self):
        self.jobs = PublicationJobs(InMemoryRegistry())

    def test_duplicate_submit_retains_job_and_never_stores_credentials(self):
        first = self.jobs.submit('demo', 'digest', 'reviewer')
        self.assertEqual(first, self.jobs.submit('demo', 'digest', 'reviewer'))
        self.assertNotIn('approval_token', first)
        with self.assertRaises(ValueError):
            self.jobs.submit('demo', 'changed', 'reviewer')

    def test_queue_runs_once_and_retains_verified_result(self):
        self.jobs.submit('demo', 'digest', 'reviewer')
        calls = []
        self.jobs.run_once(lambda job: calls.append(job) or {'status': 'published', 'publication_id': 'digest', 'ontology_id': 'demo'}, lambda _: {})
        self.jobs.run_once(lambda _: self.fail('Completed write replayed'), lambda _: {})
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.jobs.get('demo')['status'], 'published')

    def test_interrupted_write_is_verified_without_replay(self):
        job = self.jobs.submit('demo', 'digest', 'reviewer')
        self.jobs.registry.put('demo', {**job, 'status': 'running'})
        self.jobs.run_once(lambda _: self.fail('Interrupted write replayed'),
            lambda _: {'status': 'published', 'publication_id': 'digest', 'ontology_id': 'demo'})
        self.assertEqual(self.jobs.get('demo')['status'], 'published')

    def test_recovery_rejects_receipt_for_another_ontology(self):
        job = self.jobs.submit('demo', 'digest', 'reviewer')
        self.jobs.registry.put('demo', {**job, 'status': 'running'})
        self.jobs.run_once(lambda _: self.fail('Interrupted write replayed'),
            lambda _: {'status': 'published', 'publication_id': 'digest', 'ontology_id': 'other'})
        self.assertEqual(self.jobs.get('demo')['status'], 'running')

    def test_changed_artifact_does_not_leave_reconciliation_stuck(self):
        job = self.jobs.submit('demo', 'digest', 'reviewer')
        self.jobs.registry.put('demo', {**job, 'status': 'reconciliation_required'})
        self.jobs.run_once(lambda _: self.fail('Automatic replay'),
            lambda _: {'status': 'published', 'publication_id': 'new-digest', 'ontology_id': 'demo'})
        self.assertEqual(self.jobs.get('demo')['status'], 'failed')
        self.assertEqual(self.jobs.submit('demo', 'new-digest', 'reviewer')['status'], 'queued')

    def test_failed_dispatch_requires_reconciliation(self):
        self.jobs.submit('demo', 'digest', 'reviewer')
        def fail(_):
            raise TimeoutError('private upstream body')
        self.jobs.run_once(fail, lambda _: {'status': 'unverified'})
        self.assertEqual(self.jobs.get('demo')['status'], 'reconciliation_required')
        self.assertNotIn('private upstream body', str(self.jobs.get('demo')))

    def test_only_exact_queued_job_can_be_cancelled(self):
        job = self.jobs.submit('demo', 'digest', 'reviewer')
        with self.assertRaises(ValueError):
            self.jobs.cancel('demo', 'wrong')
        self.assertEqual(self.jobs.cancel('demo', job['job_id'])['status'], 'cancelled')
        self.jobs.run_once(lambda _: self.fail('Cancelled write dispatched'), lambda _: {})

    def test_wrong_artifact_receipt_cannot_complete_job(self):
        self.jobs.submit('demo', 'digest', 'reviewer')
        self.jobs.run_once(lambda _: {'status': 'published', 'publication_id': 'wrong', 'ontology_id': 'demo'},
                           lambda _: {'status': 'unverified'})
        self.assertEqual(self.jobs.get('demo')['status'], 'reconciliation_required')

    def test_idle_missing_receipt_requires_new_explicit_submission(self):
        job = self.jobs.submit('demo', 'digest', 'reviewer')
        self.jobs.registry.put('demo', {**job, 'status': 'running'})
        self.jobs.run_once(lambda _: self.fail('Automatic replay'), lambda _: {'status': 'not_published'})
        self.assertEqual(self.jobs.get('demo')['status'], 'failed')

    def test_queued_job_status_does_not_require_a_graph_request(self):
        job = self.jobs.submit('demo', 'digest', 'reviewer')
        tree = ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if getattr(node, 'name', '') == 'ontology_publication_status')
        function.decorator_list = []
        async def thread(fn, *args):
            return fn(*args)
        scope = {'__name__': 'backend.ontology_service.router', '__package__': 'backend.ontology_service',
                 'run_in_threadpool': thread}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<status>', 'exec'), scope)
        with patch('backend.ontology_service.publication_jobs.publication_jobs', self.jobs):
            status = asyncio.run(scope['ontology_publication_status']('demo'))
        self.assertEqual(status['job_id'], job['job_id'])
        self.assertEqual(status['phase'], 'queued')


if __name__ == '__main__':
    unittest.main()
