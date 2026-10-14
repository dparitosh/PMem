"""Durable publication requests; uncertain writes require receipt reconciliation."""
from datetime import datetime, timezone
import logging
import uuid
from backend.mesh_store import PostgresRegistry


def now():
    return datetime.now(timezone.utc).isoformat()


class PublicationJobs:
    def __init__(self, registry=None):
        self.registry = registry or PostgresRegistry('ontology_publication_jobs_v1')

    def submit(self, ontology_id, artifact_sha256, actor):
        with self.registry.advisory_lock(ontology_id) as acquired:
            if not acquired:
                raise ValueError('Publication worker is active; refresh its status')
            previous = self.registry.get(ontology_id)
            if previous and previous['status'] in {'queued', 'running', 'reconciliation_required'}:
                if previous['artifact_sha256'] != artifact_sha256:
                    raise ValueError('An earlier artifact publication must be reconciled first')
                return previous
            job = {'job_id': str(uuid.uuid4()), 'ontology_id': ontology_id,
                   'artifact_sha256': artifact_sha256, 'approved_by': actor,
                   'status': 'queued', 'created_at': now(), 'updated_at': now()}
            self.registry.put(ontology_id, job)
            return job

    def get(self, ontology_id):
        return self.registry.get(ontology_id)

    def cancel(self, ontology_id, job_id):
        with self.registry.advisory_lock(ontology_id) as acquired:
            if not acquired:
                raise ValueError('Publication already executing; completed writes cannot be cancelled')
            job = self.get(ontology_id)
            if not job or job['job_id'] != job_id or job['status'] != 'queued':
                raise ValueError('Only the selected queued publication can be cancelled')
            result = {**job, 'status': 'cancelled', 'updated_at': now()}
            self.registry.put(ontology_id, result)
            return result

    def run_once(self, execute, verify):
        # A session advisory lock survives long jobs, and is released by process
        # death. Never replay a possibly committed write after a worker restart.
        for state in ('running', 'queued', 'reconciliation_required'):
            for candidate in self.registry.find_by_field('status', state, limit=20):
                identity = candidate['ontology_id']
                with self.registry.advisory_lock(identity) as acquired:
                    if not acquired:
                        continue
                    job = self.get(identity)
                    if not job or job['job_id'] != candidate['job_id'] or job['status'] != state:
                        continue
                    try:
                        if state != 'queued':
                            receipt = verify(identity)
                            if (receipt.get('status') == 'published'
                                    and receipt.get('publication_id') == job['artifact_sha256']
                                    and receipt.get('ontology_id') == identity):
                                result = {**job, 'status': 'published', 'result': receipt}
                            elif receipt.get('status') in {'not_published', 'not_verified'}:
                                result = {**job, 'status': 'failed', 'error_type': 'InterruptedPublication',
                                          'recovery_action': 'review_and_submit_again'}
                            elif receipt.get('status') == 'published' and receipt.get('ontology_id') == identity:
                                result = {**job, 'status': 'failed', 'error_type': 'ArtifactChanged',
                                          'recovery_action': 'review_and_submit_again'}
                            else:
                                continue
                        else:
                            job = {**job, 'status': 'running', 'updated_at': now()}
                            self.registry.put(identity, job)
                            receipt = execute(job)
                            if (receipt.get('status') != 'published'
                                    or receipt.get('publication_id') != job['artifact_sha256']
                                    or receipt.get('ontology_id') != identity):
                                raise RuntimeError('Publication receipt was not verified')
                            result = {**job, 'status': 'published', 'result': receipt}
                    except Exception as exc:
                        logging.getLogger(__name__).error('Publication job failed job_id=%s error_type=%s', job['job_id'], type(exc).__name__)
                        result = {**job, 'status': 'reconciliation_required', 'error_type': type(exc).__name__,
                                  'recovery_action': 'verify_graph_receipt'}
                    self.registry.put(identity, {**result, 'updated_at': now()})


publication_jobs = PublicationJobs()
