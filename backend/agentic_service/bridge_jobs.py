"""Durable reviewed Bridge jobs. Only the graph service may publish mappings."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from backend.mesh_store import PostgresRegistry


class BridgeConflict(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class BridgeJobs:
    def __init__(self, store=None, source=None, graph=None):
        self.store = store or PostgresRegistry('semantic_bridge_jobs_v1')
        self.source = source or BridgeSource()
        self.graph = graph or GraphBridgeClient()

    def get(self, job_id):
        job = self.store.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return copy.deepcopy(job)

    def preview(self, ontology_id, import_task_id, actor):
        if not ontology_id or not import_task_id:
            raise ValueError('Select an ontology and an imported instance.')
        snapshot, candidates = self.source.preview(ontology_id, import_task_id)
        if len(candidates) > 2000:
            raise ValueError('Preview exceeds 2000 candidates. Narrow the imported source before review.')
        rows = {}
        for candidate in candidates:
            row = dict(candidate)
            row.pop('selected_for_apply', None)
            row.pop('approvedByUser', None)
            row['candidate_id'] = digest(row)
            row['eligible'] = bool(row.get('ontology_class_element_id') and
                not row.get('validation_errors') and row.get('validation_status') != 'invalid')
            rows[row['candidate_id']] = row
        preview_id = 'bridge-preview-' + uuid4().hex
        job = {'job_id': preview_id, 'kind': 'preview', 'status': 'ready',
               'publication_job_id': preview_id.replace('bridge-preview-', 'bridge-publication-', 1),
               'ontology_id': ontology_id, 'import_task_id': import_task_id,
               'created_by': actor, 'created_at': now(), 'snapshot': snapshot,
               'candidates': list(rows.values())}
        job['preview_digest'] = digest(job)
        self.store.put(preview_id, job)
        return job

    def publish(self, preview_id, approved_ids, actor):
        if not isinstance(approved_ids, list) or not approved_ids or not all(isinstance(x, str) for x in approved_ids):
            raise ValueError('Select at least one candidate from the saved preview.')
        if len(set(approved_ids)) != len(approved_ids):
            raise ValueError('Duplicate candidate IDs are not allowed.')
        job_id = preview_id.replace('bridge-preview-', 'bridge-publication-', 1)
        with self.store.advisory_lock(job_id) as acquired:
            if not acquired:
                raise BridgeConflict('Publication is already running. Refresh its status.')
            preview = self.get(preview_id)
            if preview.get('kind') != 'preview' or digest({k:v for k,v in preview.items() if k != 'preview_digest'}) != preview.get('preview_digest'):
                raise BridgeConflict('Preview integrity check failed. Create a new preview.')
            by_id = {c['candidate_id']: c for c in preview['candidates']}
            if any(i not in by_id or not by_id[i]['eligible'] for i in approved_ids):
                raise ValueError('Approval contains an unknown or invalid candidate.')
            selected = sorted(approved_ids)
            existing = self.store.get(job_id)
            if existing and existing['approved_ids'] != selected:
                raise BridgeConflict('This preview already has a publication selection. Create a new preview to change it.')
            job = copy.deepcopy(existing) if existing else {
                'job_id': job_id, 'kind': 'publication', 'preview_id': preview_id,
                'status': 'approved', 'approved_ids': selected, 'approved_by': actor,
                'created_at': now(), 'attempts': 0,
                'ontology_id': preview['ontology_id'], 'import_task_id': preview['import_task_id']}
            if job['status'] == 'published':
                return job
            self.store.put(job_id, job)
            # Reconcile a committed graph transaction before checking staleness.
            # A response may have been lost after the graph committed.
            receipt = self.graph.receipt(job_id)
            if receipt:
                return self._completed(job, receipt)
            current = self.source.snapshot(preview['ontology_id'], preview['import_task_id'])
            if current != preview['snapshot']:
                job.update(status='stale', error='Source or ontology changed. Create and approve a new preview.')
                self.store.put(job_id, job)
                raise BridgeConflict(job['error'])
            if job['status'] == 'stale':
                raise BridgeConflict('This preview was invalidated. Create a new preview.')
            job.update(status='publishing', attempts=job['attempts'] + 1, updated_at=now())
            job.pop('error', None)
            self.store.put(job_id, job)
            rows = [{**by_id[i], 'selected_for_apply': True, 'approvedByUser': True,
                     'validation_status': 'approved'} for i in selected]
            command = {'publication_id': job_id, 'preview_id': preview_id,
                       'ontology_id': preview['ontology_id'],
                       'approved_by': job['approved_by'], 'snapshot': preview['snapshot'], 'rows': rows}
            command['request_digest'] = digest(command)
            job['request_digest'] = command['request_digest']
            self.store.put(job_id, job)
            try:
                receipt = self.graph.publish(command)
            except Exception:
                job.update(status='retryable', error='Publication response unavailable. Retry the same selection to reconcile its receipt.', updated_at=now())
                self.store.put(job_id, job)
                raise
            return self._completed(job, receipt)

    def _completed(self, job, receipt):
        if receipt.get('request_digest') != job.get('request_digest'):
            raise BridgeConflict('Graph receipt does not match the approved publication.')
        job.update(status='published', receipt=receipt, updated_at=now())
        job.pop('error', None)
        self.store.put(job['job_id'], job)
        return job


class BridgeSource:
    def _read(self, ontology_id, import_id):
        from backend.Services.semantic_workflow_service import SemanticWorkflowService as service
        from backend.Services.unified_data_import import UnifiedDataImportService
        ontology_id = service._resolve_ontology_id(ontology_id)
        meta = service._ontology_metadata(ontology_id)
        task = service._load_import_task({'task_id': import_id})
        scope = meta.get('prefix') or meta.get('ontology_prefix') or ontology_id
        # Include live graph IDs/type metadata as well as retained ontology bytes.
        terms = service._load_ontology_term_lookup(scope)
        classes = UnifiedDataImportService._load_ontology_class_lookup(scope)
        snapshot = {'source': digest(task.get('parsed_rows') or []),
                    'ontology': digest([ontology_id, scope, service._read_ontology_file(meta), terms, classes])}
        return service, task, scope, snapshot

    def snapshot(self, ontology_id, import_id):
        return self._read(ontology_id, import_id)[3]

    def preview(self, ontology_id, import_id):
        service, task, scope, snapshot = self._read(ontology_id, import_id)
        candidates = service._build_link_candidates(task.get('parsed_rows') or [], scope, import_id, import_task=task)
        if snapshot != self.snapshot(ontology_id, import_id):
            raise BridgeConflict('Source changed while previewing. Retry preview.')
        return snapshot, candidates


class GraphBridgeClient:
    def _request(self, method, path, **kwargs):
        import os
        import httpx
        base = os.environ.get('GRAPH_SERVICE_URL', '').rstrip('/')
        token = os.environ.get('GRAPH_PUBLICATION_TOKEN', '')
        if not base or not token:
            raise RuntimeError('Graph publication service credentials are not configured.')
        # Existing peer configuration ends in /api/v1; graph routes own /graph.
        if base.endswith('/api/v1'):
            base = base[:-7]
        with httpx.Client(timeout=120) as client:
            response = client.request(method, base + '/api/v1/graph/bridge/' + path,
                                      headers={'Authorization': 'Bearer ' + token}, **kwargs)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def receipt(self, job_id):
        return self._request('GET', 'publications/' + job_id)

    def publish(self, command):
        result = self._request('POST', 'publications', json=command)
        if not result:
            raise RuntimeError('Graph publication endpoint is unavailable.')
        return result
