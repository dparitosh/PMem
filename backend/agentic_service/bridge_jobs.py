"""Durable reviewed Bridge jobs. Only the graph service may publish mappings."""
from __future__ import annotations

import copy
from contextlib import nullcontext
from datetime import datetime, timezone
from uuid import uuid4

from backend.depo_platform.network import bounded_timeout_seconds, gateway_subscription_headers
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.bridge_contract import BridgeConflict, digest, canonical_lookup


def now():
    return datetime.now(timezone.utc).isoformat()


class BridgeJobs:
    def __init__(self, store=None, source=None, graph=None, policy_evaluator=None, holds=None, learning_store=None):
        self.store = store or PostgresRegistry('semantic_bridge_jobs_v1')
        from backend.mesh_store import InMemoryRegistry
        self.holds = holds if holds is not None else (PostgresRegistry('semantic_bridge_holds_v1') if store is None else InMemoryRegistry())
        self.learning_store = learning_store if learning_store is not None else (PostgresRegistry('agentic_learning_reviews_v1') if store is None else InMemoryRegistry())
        self.source = source or BridgeSource()
        self.graph = graph or GraphBridgeClient()
        from backend.depo_platform.decision_policy import assess_decisions
        self.policy_evaluator = policy_evaluator or assess_decisions

    def get(self, job_id):
        job = self.store.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return copy.deepcopy(job)

    def preview(self, ontology_id, import_task_id, actor, manual_mappings=None, candidate_offset=0):
        if not ontology_id or not import_task_id:
            raise ValueError('Select an ontology and an imported instance.')
        partition_reader = getattr(self.source, 'preview_partition', None)
        partition = None
        if callable(partition_reader):
            snapshot, candidates, partition = partition_reader(ontology_id, import_task_id, manual_mappings, candidate_offset)
        else:
            snapshot, candidates = self.source.preview(ontology_id, import_task_id)
        if manual_mappings and partition is None:
            candidates.extend(self.source.manual_candidates(ontology_id, import_task_id, manual_mappings))
            if snapshot != self.source.snapshot(ontology_id, import_task_id):
                raise BridgeConflict('Source changed while resolving manual mappings. Retry preview.')
        if type(candidate_offset) is not int or candidate_offset < 0:
            raise ValueError('candidate_offset must be a nonnegative integer')
        total = partition['total_candidates'] if partition else len(candidates)
        if candidate_offset and candidate_offset >= total:
            raise ValueError('Candidate partition is no longer available; start a new preview')
        if partition is None and (total > 2000 or candidate_offset):
            candidates = sorted(candidates, key=digest)[candidate_offset:candidate_offset + 2000]
        rows = {}
        for candidate in candidates:
            row = dict(candidate)
            row.pop('selected_for_apply', None)
            row.pop('approvedByUser', None)
            row['candidate_id'] = digest(row)
            row['eligible'] = bool(all(row.get(key) for key in ('import_id', 'import_row_key', 'ontology_class_element_id')) and
                row.get('target_ontology_type') in {'Class', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty'} and
                not row.get('validation_errors') and row.get('validation_status') != 'invalid')
            rows[row['candidate_id']] = row
        preview_id = 'bridge-preview-' + uuid4().hex
        job = {'job_id': preview_id, 'kind': 'preview', 'status': 'ready',
               'publication_job_id': preview_id.replace('bridge-preview-', 'bridge-publication-', 1),
               'ontology_id': ontology_id, 'import_task_id': import_task_id,
               'created_by': actor, 'created_at': now(), 'snapshot': snapshot,
               'candidates': list(rows.values())}
        job['partition'] = {'offset': candidate_offset, 'total_candidates': total,
                            'next_offset': candidate_offset + 2000 if candidate_offset + 2000 < total else None}
        job['recommendation_summary'] = {'total': len(rows),
            'eligible': sum(1 for row in rows.values() if row['eligible']),
            'requires_review': True,
            'definition': 'Recommendations are evidence for user review, not publication approval.'}
        job['preview_digest'] = digest(job)
        self.store.put(preview_id, job)
        return job

    def _semantic_support(self, preview, *, locked=False):
        reader = getattr(self.source, 'semantic_support', None)
        support = reader(preview['ontology_id']) if callable(reader) else {'disposition': 'unverified'}
        key = digest({'ontology_id': preview['ontology_id'], 'ontology_snapshot': preview['snapshot']['ontology']})
        with (nullcontext(True) if locked else self.holds.advisory_lock(key)) as acquired:
            if acquired is False: raise BridgeConflict('Semantic decision is being updated; refresh before publication')
            prior = self.holds.get(key)
            if prior:
                retained = copy.deepcopy(prior['assessment'])
                if support.get('consistency_verified') is True and support.get('status') == 'inconsistent':
                    retained = copy.deepcopy(support)
                    prior['assessment'] = retained
                    self.holds.put(key, prior)
                # Exact checks may resolve an incomplete sample, but an outage
                # cannot erase a known contradiction or change its dependency binding.
                if (support.get('consistency_verified') is True
                    and support.get('artifact_sha256') == retained.get('artifact_sha256')
                    and support.get('foundation') == retained.get('foundation')
                    and support.get('status') == retained.get('status') == 'consistent'):
                    checks = retained.setdefault('target_checks', {})
                    for target in support.get('unsatisfiable_classes', []):
                        checks[target] = 'unsatisfiable'
                    for target, status in (support.get('target_checks') or {}).items():
                        if checks.get(target) != 'unsatisfiable' and target not in retained.get('unsatisfiable_classes', []):
                            checks[target] = status
                    prior['assessment'] = retained
                    self.holds.put(key, prior)
                # A known conflict cannot be cleared by an outage, a new caller or
                # a different proposal against the same retained model snapshot.
                return {**retained, 'hold_retained': True,
                    'current_evidence_status': support.get('status', 'unknown'),
                    'business_summary': 'An established model conflict remains unresolved for this revision. Prepare a new review after correcting and verifying the model.'}
            if support.get('consistency_verified') is True and support.get('disposition') == 'conflict':
                self.holds.put(key, {'ontology_id': preview['ontology_id'], 'snapshot': preview['snapshot']['ontology'],
                    'assessment': copy.deepcopy(support), 'created_at': now(), 'status': 'held'})
            return support

    def evaluate_policy(self, preview_id):
        """Deterministic steward decision over an immutable saved preview."""
        preview = self.get(preview_id)
        if preview.get('kind') != 'preview' or digest({k:v for k,v in preview.items() if k != 'preview_digest'}) != preview.get('preview_digest'):
            raise BridgeConflict('Preview integrity check failed. Create a new preview.')
        from backend.depo_platform.decision_policy import decision
        shared = self.policy_evaluator('instance_bridge', [decision(row.get('confidence'),
            candidate_id=row['candidate_id'], candidate_label=str(row.get('source_term') or '') + ' -> ' + str(row.get('ontology_term') or ''), preview_digest=preview['preview_digest'],
            ontology_id=preview['ontology_id'], import_task_id=preview['import_task_id']) for row in preview['candidates']]) if preview['candidates'] else {'status': 'not_applicable', 'blocking': False, 'checks': []}
        shared_held = set(shared.get('blocked_decision_indices', [c['decision_index'] for c in shared['checks'] if not c['compliant']]))
        support = self._semantic_support(preview)
        decisions, accepted = [], []
        sources = {}
        for row in preview['candidates']:
            key = (row.get('import_row_key'), row.get('source_term'), row.get('source_type'))
            if row.get('rank') == 1:
                sources[key] = sources.get(key, 0) + 1
        for row in preview['candidates']:
            key = (row.get('import_row_key'), row.get('source_term'), row.get('source_type'))
            from backend.ontology_service.governance import bridge_findings
            checks = bridge_findings(row)
            from backend.depo_platform.semantic_support import target_conflict
            if target_conflict(support, row): checks.append('target_ontology_logical_conflict')
            if not row.get('eligible'): checks.append('invalid_target_or_source')
            if row.get('validation_status') != 'auto_approved': checks.append('not_automatically_validated')
            if row.get('validation_warnings'): checks.append('validation_warning')
            if row.get('ambiguous') or sources.get(key, 0) != 1: checks.append('ambiguous_target')
            if row.get('generic_match') or row.get('rank') != 1: checks.append('non_specific_or_alternative_match')
            confidence = row.get('confidence')
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not .9 <= confidence <= 1:
                checks.append('insufficient_confidence')
            index = len(decisions)
            if shared['blocking'] and (shared['status'] == 'unavailable' or index in shared_held):
                checks.append('decision_policy_' + shared['status'])
            if not checks: accepted.append(row['candidate_id'])
            decisions.append({'candidate_id': row['candidate_id'], 'decision': 'hold' if checks else 'publish', 'reasons': checks})
        try:
            from .learning_review import LearningReview,pattern
            learning = LearningReview(self,self.learning_store).support(preview['ontology_id'],preview['import_task_id'])
            patterns={digest(pattern(row)) for row in preview['candidates']}
            learning['lessons']=[row for row in learning['lessons'] if digest(row['mapping_pattern']) in patterns]
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning('Approved lesson read unavailable: %s',type(exc).__name__)
            learning = {'status':'unavailable','lessons':[],'advisory_only':True,'publication_authorized':False}
        return {'policy': 'validated-only-v1', 'preview_id': preview_id, 'learning_support':learning,
                'accepted_ids': sorted(accepted), 'held_count': len(decisions)-len(accepted),
                'decisions': decisions, 'status': 'ready' if accepted else 'held', 'decision_policy': shared,
                'semantic_support': support,
                'governance': {'evaluator': 'deterministic-steward-policy', 'policy_version': 'steward-governance-v1', 'scope': 'instance classification candidates',
                    'identity_review': 'distinct from class assignment', 'abox_shacl_validation': 'not_established_by_mapping_preview',
                    'provenance': {'ontology_id': preview['ontology_id'], 'import_task_id': preview['import_task_id'],
                                   'snapshot': preview['snapshot'], 'preview_digest': preview['preview_digest']},
                    'confidence_kind': 'matching evidence; not calibrated probability', 'automatic_changes_applied': False}}

    def publish_automatic(self, preview_id, actor):
        if not isinstance(preview_id, str) or not preview_id.startswith('bridge-preview-'):
            raise ValueError('Select a saved Semantic Bridge preview before publication.')
        # A policy change cannot turn an already committed receipt into an apparent failure.
        job_id = preview_id.replace('bridge-preview-', 'bridge-publication-', 1)
        existing = self.store.get(job_id)
        if existing and existing.get('request_digest') and self.graph.receipt(job_id):
            return {**self.reconcile_receipt(job_id, existing['approved_ids']),
                    'policy_decision': existing.get('approval_policy')}
        decision = self.evaluate_policy(preview_id)
        if not decision['accepted_ids']:
            return {**decision, 'status': 'held', 'applied_links': 0}
        return {**self.publish(preview_id, decision['accepted_ids'], actor, approval_policy=decision),
                'policy_decision': decision}

    def publish(self, preview_id, approved_ids, actor, approval_policy=None):
        if not isinstance(preview_id, str) or not preview_id.startswith('bridge-preview-'):
            raise ValueError('Select a saved Semantic Bridge preview before publication.')
        preview = self.get(preview_id)
        key = digest({'ontology_id': preview['ontology_id'], 'ontology_snapshot': preview['snapshot']['ontology']})
        # Serialize the final assessment and graph action against new semantic
        # holds for this revision, including other previews/controllers.
        with self.holds.advisory_lock(key) as acquired:
            if acquired is False:
                raise BridgeConflict('Semantic review or publication is active; refresh before retrying')
            return self._publish(preview_id, approved_ids, actor, approval_policy)

    def _publish(self, preview_id, approved_ids, actor, approval_policy=None):
        if not isinstance(preview_id, str) or not preview_id.startswith('bridge-preview-'):
            raise ValueError('Select a saved Semantic Bridge preview before publication.')
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
            from backend.ontology_service.governance import bridge_findings
            if any(bridge_findings(by_id[key]) for key in approved_ids):
                raise ValueError('Ontology Steward requires domain review for identity assertions; no automatic predicate downgrade was applied')
            selected = sorted(approved_ids)
            existing = self.store.get(job_id)
            if existing and existing['approved_ids'] != selected:
                raise BridgeConflict('This preview already has a publication selection. Create a new preview to change it.')
            job = copy.deepcopy(existing) if existing else {
                'job_id': job_id, 'kind': 'publication', 'preview_id': preview_id,
                'status': 'approved', 'approved_ids': selected, 'approved_by': actor,
                'created_at': now(), 'attempts': 0,
                'ontology_id': preview['ontology_id'], 'import_task_id': preview['import_task_id']}
            if approval_policy is not None:
                if existing and existing.get('approval_policy') != approval_policy:
                    raise BridgeConflict('Publication approval policy changed. Create a new preview.')
                job['approval_policy'] = copy.deepcopy(approval_policy)
            if job['status'] == 'published':
                receipt = self.graph.receipt(job_id)
                if receipt:
                    return self._completed(job, receipt)
                job.update(status='stale', error='Published graph receipt is missing. Create and approve a new preview.', updated_at=now())
                self.store.put(job_id, job)
                raise BridgeConflict(job['error'])
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
            reader = getattr(self.source, 'semantic_support', None)
            if callable(reader):
                from backend.depo_platform.semantic_support import target_conflict
                support = self._semantic_support(preview, locked=True)
                job['semantic_support'] = support
                if any(target_conflict(support, by_id[key]) for key in selected):
                    job.update(status='held', error='The model has a logical contradiction or unresolved target satisfiability; check the selected class and review again.')
                    self.store.put(job_id, job)
                    raise ValueError(job['error'])
            # Recheck current central policy for manual and automatic writes, after receipt reconciliation.
            from backend.depo_platform.decision_policy import decision
            shared = self.policy_evaluator('instance_bridge', [decision(by_id[i].get('confidence'),
                candidate_id=i, candidate_label=str(by_id[i].get('source_term') or '') + ' -> ' + str(by_id[i].get('ontology_term') or ''), preview_digest=preview['preview_digest'], ontology_id=preview['ontology_id'],
                import_task_id=preview['import_task_id'], approved_by=actor) for i in selected])
            job['decision_policy'] = shared
            if shared['blocking']:
                job.update(status='held', error='Semantica decision policy holds publication; review the retained policy findings.', updated_at=now())
                self.store.put(job_id, job)
                raise ValueError(job['error'])
            job.update(status='publishing', attempts=job['attempts'] + 1, updated_at=now())
            job.pop('error', None)
            self.store.put(job_id, job)
            rows = [{**by_id[i], 'selected_for_apply': True, 'approvedByUser': True,
                     'validation_status': 'approved'} for i in selected]
            command = {'publication_id': job_id, 'preview_id': preview_id,
                       'ontology_id': preview['ontology_id'],
                       'approved_by': job['approved_by'], 'snapshot': preview['snapshot'], 'rows': rows}
            if job.get('semantic_support', {}).get('consistency_verified') is True:
                command['semantic_binding'] = {key: job['semantic_support'].get(key)
                    for key in ('artifact_sha256', 'evidence_id', 'foundation')}
            command['request_digest'] = digest(command)
            job['request_digest'] = command['request_digest']
            self.store.put(job_id, job)
            try:
                receipt = self.graph.publish(command)
            except BridgeConflict as exc:
                job.update(status='stale', error=str(exc), updated_at=now())
                self.store.put(job_id, job)
                raise
            except Exception:
                job.update(status='retryable', error='Publication response unavailable. Retry the same selection to reconcile its receipt.', updated_at=now())
                self.store.put(job_id, job)
                raise
            return self._completed(job, receipt)

    def reconcile_receipt(self, job_id, approved_ids):
        """Reconcile a verified graph receipt without dispatching publication."""
        with self.store.advisory_lock(job_id) as acquired:
            if not acquired:
                raise BridgeConflict('Publication is already running. Refresh its status.')
            job = self.get(job_id)
            if not approved_ids or set(job.get('approved_ids', [])) != set(approved_ids):
                raise BridgeConflict('Receipt selection does not match the retained approved candidates')
            receipt = self.graph.receipt(job_id)
            if not isinstance(receipt, dict):
                raise BridgeConflict('No matching graph publication receipt is available')
            return self._completed(job, receipt)

    def _completed(self, job, receipt):
        if (not isinstance(receipt, dict) or not job.get('request_digest') or
                receipt.get('request_digest') != job['request_digest'] or
                receipt.get('publication_id') != job['job_id'] or
                type(receipt.get('applied_links')) is not int or
                receipt['applied_links'] != len(job['approved_ids']) or
                receipt.get('approved_by') != job['approved_by']):
            raise BridgeConflict('Graph receipt does not match the approved publication.')
        if job.get('status') == 'published' and job.get('receipt') == receipt:
            return job
        job.update(status='published', receipt=receipt, updated_at=now())
        job.pop('error', None)
        self.store.put(job['job_id'], job)
        return job


class BridgeSource:
    def model_revision(self, ontology_id):
        from urllib.parse import quote
        from backend.depo_platform.peer_http import peer_response
        from backend.depo_platform.service_urls import service_url
        from backend.depo_platform.network import service_bearer_headers
        import re
        base=service_url('ONTOLOGY_SERVICE_URL','http://127.0.0.1:8011/api/v1').rstrip('/')
        if not base.endswith('/api/v1'):base+='/api/v1'
        endpoint=base+'/ontologies/'+quote(ontology_id,safe='')+'/revision'
        response=peer_response('GET',endpoint,budget=5,response_limit=65536,
            headers=service_bearer_headers('GRAPH_READ_TOKEN',service_name='Learning model revision',endpoint=endpoint))
        response.raise_for_status();body=response.json()
        if body.get('ontology_id')!=ontology_id or not re.fullmatch('[0-9a-f]{64}',str(body.get('artifact_sha256',''))):
            raise ValueError('Invalid owning-service model revision')
        if body.get('status')=='superseded' or body.get('lifecycle_status') in {'retired','deprecated'}:
            raise ValueError('Select a current ontology before reusing review hints')
        return {key:body[key] for key in ('ontology_id','artifact_sha256','semantic_dependencies','status','lifecycle_status') if key in body}

    def semantic_support(self, ontology_id):
        import os
        from backend.depo_platform.semantic_support import read_support
        token = os.getenv('GRAPH_READ_TOKEN', '')
        return read_support(ontology_id, {'Authorization': 'Bearer ' + token} if token else {})

    def _request(self, action, ontology_id, import_id, mappings=None, candidate_offset=0):
        from backend.depo_platform.peer_http import peer_response
        from backend.depo_platform.service_urls import service_url
        from backend.depo_platform.network import service_bearer_headers
        base = service_url('INGESTION_SERVICE_URL','http://127.0.0.1:8014/api/v1')
        if not base.endswith('/api/v1'): base += '/api/v1'
        endpoint = base + '/bridge/source'
        response = peer_response('POST',endpoint,budget=bounded_timeout_seconds('BRIDGE_SOURCE_TIMEOUT_SECONDS',default=300,maximum=900),
            headers=service_bearer_headers('INGESTION_WRITE_TOKEN',service_name='bridge source',endpoint=endpoint),
            json={'operation':action,'ontology_id':ontology_id,'import_task_id':import_id,'mappings':mappings or [],'candidate_offset':candidate_offset})
        if response.status_code == 409: raise BridgeConflict('Source changed; create a new preview')
        response.raise_for_status()
        result = response.json()
        if not isinstance(result,dict): raise ValueError('Invalid bridge source response')
        return result

    def snapshot(self, ontology_id, import_id):
        result = self._request('snapshot',ontology_id,import_id)
        snapshot = result.get('snapshot')
        if not isinstance(snapshot,dict) or not all(isinstance(snapshot.get(key),str) for key in ('source','ontology')):
            raise ValueError('Invalid bridge source snapshot')
        return snapshot

    def preview(self, ontology_id, import_id):
        result = self._request('preview',ontology_id,import_id)
        if not isinstance(result.get('snapshot'),dict) or not isinstance(result.get('candidates'),list):
            raise ValueError('Invalid bridge source preview')
        return result['snapshot'], result['candidates']

    def preview_partition(self, ontology_id, import_id, mappings=None, candidate_offset=0):
        result = self._request('preview', ontology_id, import_id, mappings, candidate_offset)
        partition = result.get('partition')
        candidates = result.get('candidates')
        if (not isinstance(result.get('snapshot'), dict) or not isinstance(candidates, list) or len(candidates) > 2000
                or not isinstance(partition, dict) or partition.get('offset') != candidate_offset
                or type(partition.get('total_candidates')) is not int or partition['total_candidates'] < candidate_offset + len(candidates)
                or partition.get('next_offset') != (candidate_offset + 2000 if candidate_offset + 2000 < partition['total_candidates'] else None)):
            raise ValueError('Invalid bridge source partition')
        return result['snapshot'], candidates, partition

    def manual_candidates(self, ontology_id, import_id, mappings):
        result = self._request('manual',ontology_id,import_id,mappings)
        if not isinstance(result.get('candidates'),list): raise ValueError('Invalid bridge source candidates')
        return result['candidates']


class GraphBridgeClient:
    def _request(self, method, path, **kwargs):
        import os
        base = os.environ.get('GRAPH_SERVICE_URL', '').rstrip('/')
        token = os.environ.get('GRAPH_PUBLICATION_TOKEN', '')
        if not base or not token:
            raise RuntimeError('Graph publication service credentials are not configured.')
        # Existing peer configuration ends in /api/v1; graph routes own /graph.
        if base.endswith('/api/v1'):
            base = base[:-7]
        endpoint = base + '/api/v1/graph/bridge/' + path
        from backend.depo_platform.peer_http import peer_response
        response = peer_response(method, endpoint,
            budget=bounded_timeout_seconds('GRAPH_PUBLICATION_TIMEOUT_SECONDS', default=180),
            headers={**gateway_subscription_headers(endpoint), 'Authorization':'Bearer '+token}, **kwargs)
        # A missing receipt is expected only for an idempotency lookup. A POST
        # route mismatch must remain visible instead of being misreported as a
        # recoverable publication response loss.
        if method == 'GET' and response.status_code == 404:
            return None
        if method == 'POST' and response.status_code == 409:
            raise BridgeConflict('Graph rejected the saved mapping because its source, target or publication state changed. Create a new preview.')
        response.raise_for_status()
        return response.json()

    def receipt(self, job_id):
        return self._request('GET', 'publications/' + job_id)

    def publish(self, command):
        result = self._request('POST', 'publications', json=command)
        if not result:
            raise RuntimeError('Graph publication endpoint is unavailable.')
        return result
