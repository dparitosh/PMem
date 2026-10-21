"""Durable merge planning and validation, owned by the ontology service lifespan."""
import hashlib
import pickle
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


def child_result_limit(module):
    if module == 'backend.ontology_service.merge_preparation':
        from backend.depo_platform.upload_limits import ontology_upload_limit
        # RDF serialization can expand input, and the result includes bounded
        # mapping/delta evidence. This is a graph result, not a small report.
        return 4 * ontology_upload_limit() + 8 * 1024 * 1024
    if module == 'backend.ontology_service.merge_semantics': return 8 * 1024 * 1024
    raise ValueError('Unsupported merge worker module')


def validation_child(payload, stop, timeout, module='backend.ontology_service.merge_semantics'):
    # Files prevent large RDF input or diagnostics from blocking pipe buffers.
    limit = child_result_limit(module)
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        source.write(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)); source.seek(0)
        process = subprocess.Popen([sys.executable, '-m', module],
            stdin=source, stdout=output, stderr=errors, cwd=str(Path(__file__).resolve().parents[2]))
        started = time.monotonic()
        try:
            while process.poll() is None:
                if stop.wait(.5): raise InterruptedError('Service stopping; validation will resume after restart')
                if time.monotonic() - started >= timeout:
                    raise ValueError('Background semantic validation exceeded its deadline. Review a smaller merge or adjust MERGE_BACKGROUND_TIMEOUT_SECONDS and retry.')
            if process.returncode: raise ValueError('Semantic validation worker failed; check ontology service diagnostics and installed reasoning dependencies')
            output.seek(0); data = output.read(limit + 1)
            if len(data) > limit: raise ValueError('Merge worker result exceeds its configured size limit')
            return pickle.loads(data)  # Trusted owned child output only.
        finally:
            if process.poll() is None: process.kill()
            process.wait()


class BackgroundMerges:
    def registry(self, service):
        if service.registry is None:
            raise ValueError('Background merge review requires central PostgreSQL metadata storage')
        from backend.mesh_store import PostgresRegistry
        return PostgresRegistry('ontology_merge_jobs')

    def enqueue(self, service, payload):
        registry = self.registry(service)
        identifiers = list(dict.fromkeys(payload.get('source_ontology_ids', [])))
        if not 2 <= len(identifiers) <= 16 or any(service.catalog.get(key) is None for key in identifiers):
            raise ValueError('Select 2 to 16 registered ontology sources')
        with registry.advisory_lock('enqueue') as acquired:
            if not acquired: raise ValueError('Merge queue busy; retry shortly')
            for state in ('queued', 'preparing', 'validating'):
                total, _ = registry.page(limit=1, field='status', value=state)
                if total >= 16: raise ValueError('Merge queue full; wait for existing reviews to finish')
            key = str(uuid.uuid4())
            registry.create(key, {'preview_id': key, 'payload': payload, 'status': 'queued', 'updated_at': time.time()})
        return self.status(service, key)

    def status(self, service, key):
        job = self.registry(service).get(key)
        if not job: raise ValueError('Merge review job not found')
        record = service.registry.get(key) or {}
        return {**{k: v for k, v in record.items() if k not in {'turtle', 'validation_receipt'}},
                'preview_id': key, 'background_validation': True, 'job_status': job['status'],
                'job_error': job.get('error'), 'updated_at': job['updated_at'],
                'publish_recommended': job['status'] == 'completed' and record.get('publish_recommended', False)}

    def is_complete(self, record):
        from backend.mesh_store import PostgresRegistry
        job = PostgresRegistry('ontology_merge_jobs').get(record['preview_id'])
        return bool(job and job['status'] == 'completed' and job.get('token') == record.get('validation_receipt', {}).get('token'))

    def run_once(self, service, stop):
        if service.registry is None: return
        registry = self.registry(service)
        for state in ('validating', 'preparing', 'queued'):
            _, jobs = registry.page(limit=16, field='status', value=state)
            for candidate in jobs:
                if stop.is_set(): return
                key = candidate['preview_id']
                with registry.advisory_lock(key) as acquired:
                    if not acquired: continue
                    job = registry.get(key)
                    if not job or job['status'] not in {'queued', 'preparing', 'validating'}: continue
                    token = str(uuid.uuid4())
                    def update(status, **extra):
                        job.update(status=status, token=token, updated_at=time.time(), **extra)
                        registry.put(key, job)
                    try:
                        record = service.registry.get(key)
                        if not record:
                            update('preparing')
                            from .merge_preparation import prepare
                            record = prepare(service, job['payload'], defer_semantics=True, stop=stop)
                            record.update(preview_id=key, background_validation=True)
                            service.registry.put(key, record)
                        metadata = []
                        for snapshot in record['sources']:
                            meta, content = service.catalog.read_artifact(snapshot['ontology_id'])
                            if hashlib.sha256(content).hexdigest() != snapshot['artifact_sha256']:
                                raise ValueError('Source ontology changed; generate a new merge review')
                            metadata.append(meta)
                        from .merge_semantics import validation_fingerprint
                        fingerprint = validation_fingerprint(metadata)
                        update('validating')
                        from backend.depo_platform.network import bounded_timeout_seconds
                        checks = validation_child((record['turtle'], metadata, record.get('changes', {}).get('entity_mappings', []), False),
                            stop, bounded_timeout_seconds('MERGE_BACKGROUND_TIMEOUT_SECONDS', default=1800, maximum=7200))
                        if validation_fingerprint(metadata) != fingerprint: raise ValueError('Validation shapes changed; generate a new review')
                        record['semantic_checks'] = checks
                        record['validation']['owl_rl_performed'] = checks.get('owl_rl_performed', False)
                        record['conflicts'] += checks.get('inferred_conflicts', [])
                        if not checks.get('shacl_conforms'): record['conflicts'].append({'kind': 'shacl_nonconformance'})
                        record['publish_recommended'] = not record['conflicts']
                        record['validation_receipt'] = {'token': token, 'graph_sha256': hashlib.sha256(record['turtle'].encode()).hexdigest(), 'policy_sha256': fingerprint}
                        service.registry.put(key, record)
                        update('completed')
                    except InterruptedError:
                        update('queued')
                    except Exception as exc:
                        import logging
                        logging.getLogger(__name__).error('Merge review failed job_id=%s error_type=%s', key, type(exc).__name__)
                        # Only our bounded validation errors are suitable for the browser.
                        update('failed', error=str(exc)[:500] if isinstance(exc, ValueError) else 'Merge worker failed; inspect ontology service logs')
                    return


background_merges = BackgroundMerges()
