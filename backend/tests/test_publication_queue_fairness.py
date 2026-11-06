import unittest
from datetime import datetime, timezone, timedelta
from backend.mesh_store import InMemoryRegistry
from backend.ontology_service.publication_jobs import PublicationJobs, describe_status


class QueueFairnessTests(unittest.TestCase):
    def test_unresolved_first_page_cannot_starve_later_jobs(self):
        store = InMemoryRegistry()
        now = datetime.now(timezone.utc)
        jobs = PublicationJobs(store, clock=lambda: now)
        for index in range(25):
            job = jobs.submit(f'ontology-{index:03}', 'digest', 'reviewer')
            store.put(job['ontology_id'], {**job, 'status':'running', 'attempt':1})
        visited = []
        verify = lambda identity: visited.append(identity) or {'status':'unverified'}
        for _ in range(2): jobs.run_once(lambda _: self.fail('Uncertain write replayed'), verify)
        self.assertEqual(len(set(visited)), 25)

    def test_deferred_first_page_cannot_starve_ready_job(self):
        jobs = PublicationJobs(InMemoryRegistry())
        future = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        for index in range(20):
            job = jobs.submit(f'a-{index:03}', 'digest', 'reviewer')
            jobs.registry.put(job['ontology_id'], {**job,'next_attempt_at':future})
        jobs.submit('z-ready','digest','reviewer')
        executed = []
        def execute(job):
            executed.append(job['ontology_id'])
            return {'status':'published','publication_id':'digest','ontology_id':job['ontology_id']}
        for _ in range(2): jobs.run_once(execute, lambda _: {})
        self.assertEqual(executed, ['z-ready'])

    def test_expired_job_state_is_visible_without_claiming_graph_failure(self):
        result = describe_status({'status':'unverified'}, {'status':'timed_out','job_id':'job','reconciliation_required':True})
        self.assertEqual(result['status'], 'timed_out')
        self.assertEqual(result['graph_status'], 'unverified')
        self.assertTrue(result['reconciliation_required'])
        self.assertEqual(describe_status({'status':'published'}, {'status':'timed_out'})['status'], 'published')
