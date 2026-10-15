"""Durable publication requests; uncertain writes require receipt reconciliation."""
from datetime import datetime, timezone, timedelta
import logging
import uuid
import random
import threading
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.network import publication_job_timeout_seconds, bounded_timeout_seconds


def now():
    return datetime.now(timezone.utc).isoformat()


def describe_status(result, job):
    """Keep execution state separate from the independently verified graph state."""
    if not job:
        return result
    metadata = {key: job[key] for key in ('job_id', 'deadline_at', 'next_attempt_at', 'attempt', 'recovery_action', 'reconciliation_required') if job.get(key) is not None}
    result = {**result, **metadata, 'job_status': job['status']}
    if job['status'] in {'timed_out', 'cancelled', 'failed'} and result.get('status') not in {'published', 'publishing'}:
        result = {**result, 'graph_status': result.get('status'), 'status': job['status']}
    return result


class PublicationJobs:
    def __init__(self, registry=None, clock=None):
        self.registry = registry or PostgresRegistry('ontology_publication_jobs_v1')
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._cursors = {}
        self._selection_lock = threading.Lock()

    def _candidates(self, state):
        # Rotate bounded keyset pages even when earlier jobs remain unresolved.
        with self._selection_lock:
            after = self._cursors.get(state, '')
            rows = self.registry.find_by_field('status', state, limit=20, after_key=after)
            if not rows and after:
                rows = self.registry.find_by_field('status', state, limit=20)
            self._cursors[state] = rows[-1]['ontology_id'] if rows else ''
            return rows

    def submit(self, ontology_id, artifact_sha256, actor):
        with self.registry.advisory_lock(ontology_id) as acquired:
            if not acquired:
                raise ValueError('Publication worker is active; refresh its status')
            previous = self.registry.get(ontology_id)
            if previous and (previous['status'] in {'queued', 'running', 'reconciliation_required'} or previous.get('reconciliation_required')):
                if previous['artifact_sha256'] != artifact_sha256:
                    raise ValueError('An earlier artifact publication must be reconciled first')
                return previous
            created = self.clock()
            total = publication_job_timeout_seconds()
            queue = bounded_timeout_seconds('ONTOLOGY_PUBLICATION_QUEUE_TIMEOUT_SECONDS', default=600, maximum=86400)
            job = {'job_id': str(uuid.uuid4()), 'ontology_id': ontology_id,
                   'artifact_sha256': artifact_sha256, 'approved_by': actor,
                   'status': 'queued', 'created_at': created.isoformat(), 'updated_at': created.isoformat(),
                   'deadline_at': (created + timedelta(seconds=total)).isoformat(),
                   'queue_deadline_at': (created + timedelta(seconds=min(queue, total))).isoformat()}
            self.registry.put(ontology_id, job)
            return job

    def get(self, ontology_id):
        return self.registry.get(ontology_id)

    def reconcile_terminal(self, ontology_id, publication_id, receipt=None, *, idle=False):
        """Called only after a service-authenticated graph receipt/idle check."""
        with self.registry.advisory_lock(ontology_id) as acquired:
            if not acquired: return
            job = self.get(ontology_id)
            if not job or job['status'] != 'timed_out' or job['artifact_sha256'] != publication_id:
                return
            published = (receipt and receipt.get('status') == 'published' and receipt.get('current') is True
                         and receipt.get('ontology_id') == ontology_id and receipt.get('publication_id') == publication_id)
            if published or idle:
                result = {**job, 'status':'published' if published else 'failed', 'reconciliation_required':False, 'updated_at':now()}
                if published: result['result'] = receipt
                self.registry.put(ontology_id, result)

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
            for candidate in self._candidates(state):
                identity = candidate['ontology_id']
                with self.registry.advisory_lock(identity) as acquired:
                    if not acquired:
                        continue
                    job = self.get(identity)
                    if not job or job['job_id'] != candidate['job_id'] or job['status'] != state:
                        continue
                    # Upgrade retained legacy jobs from their original creation
                    # time. A restart must never reset the overall deadline.
                    if not job.get('deadline_at'):
                        job = {**job, 'deadline_at': (datetime.fromisoformat(job['created_at'])
                            + timedelta(seconds=publication_job_timeout_seconds())).isoformat()}
                        self.registry.put(identity, job)
                    current = self.clock()
                    expired = current >= datetime.fromisoformat(job['deadline_at'])
                    if state == 'queued' and not job.get('attempt') and job.get('queue_deadline_at'):
                        expired = expired or current >= datetime.fromisoformat(job['queue_deadline_at'])
                    if expired:
                        try:
                            receipt = verify(identity) if job.get('attempt') else {}
                        except Exception:
                            receipt = {}  # Unknown writes remain blocked for manual reconciliation.
                        published = (receipt.get('status') == 'published' and receipt.get('publication_id') == job['artifact_sha256']
                                     and receipt.get('ontology_id') == identity)
                        result = {**job, 'status': 'published' if published else 'timed_out',
                                  'reconciliation_required': bool(job.get('attempt')) and not published,
                                  'recovery_action': 'none' if published else 'verify_graph_receipt' if job.get('attempt') else 'review_and_submit_again'}
                        if published: result['result'] = receipt
                        self.registry.put(identity, {**result, 'updated_at': now()})
                        continue
                    if job.get('next_attempt_at') and current < datetime.fromisoformat(job['next_attempt_at']):
                        continue
                    try:
                        if state != 'queued':
                            receipt = verify(identity)
                            if (receipt.get('status') == 'published'
                                    and receipt.get('publication_id') == job['artifact_sha256']
                                    and receipt.get('ontology_id') == identity):
                                result = {**job, 'status': 'published', 'result': receipt}
                            elif (receipt.get('status') in {'not_published', 'not_verified'}
                                  and receipt.get('resumable') is True and receipt.get('publication_idle') is True
                                  and job.get('attempt', 0) < 3):
                                # Only confirmed-idle, unpublished staging is safe
                                # to resume. Never replay an uncertain atomic write.
                                delay = random.uniform(.8, 1.2) * min(60, 5 * 2 ** job.get('attempt', 0))
                                result = {**job, 'status': 'queued', 'recovery_action': 'resume_retained_checkpoints',
                                          'next_attempt_at': (self.clock() + timedelta(seconds=delay)).isoformat()}
                            elif receipt.get('status') in {'not_published', 'not_verified'}:
                                result = {**job, 'status': 'failed', 'error_type': 'InterruptedPublication',
                                          'recovery_action': 'review_and_submit_again'}
                            elif receipt.get('status') == 'published' and receipt.get('ontology_id') == identity:
                                result = {**job, 'status': 'failed', 'error_type': 'ArtifactChanged',
                                          'recovery_action': 'review_and_submit_again'}
                            else:
                                continue
                        else:
                            job = {**job, 'status': 'running', 'attempt': job.get('attempt', 0) + 1, 'updated_at': now()}
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
                                  'recovery_action': 'verify_graph_receipt',
                                  'next_attempt_at': (self.clock() + timedelta(seconds=5)).isoformat()}
                    self.registry.put(identity, {**result, 'updated_at': now()})


publication_jobs = PublicationJobs()
