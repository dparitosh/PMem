"""Governance and response-loss tests; no live database or Spark runtime."""
import copy
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backend.agentic_service.bridge_jobs import BridgeJobs, BridgeConflict
from backend.mesh_store import InMemoryRegistry


class Source:
    revision = 'one'
    def snapshot(self, *args): return {'source': self.revision, 'ontology': 'one'}
    def preview(self, *args):
        return self.snapshot(), [dict(import_id='import', import_row_key='row',
            ontology_class_element_id='target', ontology_term='Part', source_term='part',
            source_type='Entity', target_ontology_type='Class', confidence=.6,
            selected_for_apply=False, validation_status='warning', validation_errors=[])]


class Graph:
    def __init__(self): self.receipts = {}; self.calls = []; self.lose_response = False
    def receipt(self, key): return self.receipts.get(key)
    def publish(self, command):
        self.calls.append(copy.deepcopy(command))
        result = {'publication_id': command['publication_id'], 'request_digest': command['request_digest'], 'applied_links': len(command['rows'])}
        self.receipts[command['publication_id']] = result
        if self.lose_response: raise TimeoutError('simulated lost response')
        return result


class BridgeJobTests(unittest.TestCase):
    def setUp(self):
        self.source = Source(); self.graph = Graph(); self.store = InMemoryRegistry()
        self.jobs = BridgeJobs(self.store, self.source, self.graph)
        self.preview = self.jobs.preview('ontology', 'import', 'reader')
        self.ids = [self.preview['candidates'][0]['candidate_id']]

    def test_preview_never_publishes_or_auto_selects(self):
        self.assertEqual(self.graph.calls, [])
        self.assertNotIn('selected_for_apply', self.preview['candidates'][0])
        self.assertEqual(self.preview['status'], 'ready')

    def test_unpublishable_candidates_cannot_be_approved(self):
        original = self.source.preview()[1][0]
        for changes in ({'import_row_key': ''}, {'import_id': ''}, {'target_ontology_type': 'Unsupported'}):
            with self.subTest(changes=changes):
                self.source.preview = lambda *args: (self.source.snapshot(), [{**original, **changes}])
                preview = self.jobs.preview('ontology', 'import', 'reader')
                candidate = preview['candidates'][0]
                self.assertFalse(candidate['eligible'])
                with self.assertRaises(ValueError):
                    self.jobs.publish(preview['job_id'], [candidate['candidate_id']], 'reviewer')
        self.assertEqual(self.graph.calls, [])

    def test_receipt_without_approved_digest_is_rejected(self):
        self.graph.receipts[self.preview['publication_job_id']] = {'publication_id': self.preview['publication_job_id']}
        with self.assertRaises(BridgeConflict):
            self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')
        self.assertNotEqual(self.jobs.get(self.preview['publication_job_id'])['status'], 'published')

    def test_receipt_from_different_publication_is_rejected(self):
        self.graph.lose_response = True
        with self.assertRaises(TimeoutError):
            self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')
        self.graph.receipts[self.preview['publication_job_id']]['publication_id'] = 'another-job'
        with self.assertRaises(BridgeConflict):
            self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')

    def test_snapshot_ignores_lookup_order_but_detects_target_changes(self):
        from backend.agentic_service.bridge_jobs import BridgeSource
        from backend.Services.semantic_workflow_service import SemanticWorkflowService as service
        from backend.Services.unified_data_import import UnifiedDataImportService as imports
        lookup = {'part': [{'element_id': 'one'}, {'element_id': 'two'}]}
        with patch.object(service, '_resolve_ontology_id', return_value='ontology'), \
             patch.object(service, '_ontology_metadata', return_value={'prefix': 'part'}), \
             patch.object(service, '_load_import_task', return_value={'parsed_rows': [{'id': 'one'}]}), \
             patch.object(service, '_read_ontology_file', return_value='ontology bytes'), \
             patch.object(service, '_load_ontology_term_lookup', return_value=lookup), \
             patch.object(imports, '_load_ontology_class_lookup', return_value=lookup):
            source = BridgeSource()
            before = source.snapshot('ontology', 'import')
            lookup['part'].reverse()
            self.assertEqual(before, source.snapshot('ontology', 'import'))
            lookup['part'][0]['element_id'] = 'replacement'
            self.assertNotEqual(before, source.snapshot('ontology', 'import'))

    def test_empty_unknown_duplicate_selection_rejected(self):
        for selection in ([], ['invented'], self.ids * 2):
            with self.assertRaises(ValueError): self.jobs.publish(self.preview['job_id'], selection, 'reviewer')
        self.assertEqual(self.graph.calls, [])

    def test_manual_review_of_non_auto_candidate_is_applied(self):
        result = self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')
        self.assertEqual(result['status'], 'published')
        self.assertTrue(self.graph.calls[0]['rows'][0]['approvedByUser'])
        self.assertEqual(self.jobs.get(self.preview['job_id']), self.preview)

    def test_only_selected_candidate_published(self):
        original = self.source.preview
        self.source.preview = lambda *a: (self.source.snapshot(), original()[1] + [{**original()[1][0], 'import_row_key': 'other'}])
        preview = self.jobs.preview('ontology','import','reader')
        selected = [preview['candidates'][1]['candidate_id']]
        self.jobs.publish(preview['job_id'], selected, 'reviewer')
        self.assertEqual(len(self.graph.calls[0]['rows']), 1)
        self.assertEqual(self.graph.calls[0]['rows'][0]['import_row_key'], 'other')
        with self.assertRaises(BridgeConflict): self.jobs.publish(preview['job_id'], [preview['candidates'][0]['candidate_id']], 'reviewer')

    def test_stale_source_rejected(self):
        self.source.revision = 'two'
        with self.assertRaises(BridgeConflict): self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')
        self.assertEqual(self.graph.calls, [])
        self.assertEqual(self.jobs.get(self.preview['publication_job_id'])['status'], 'stale')

    def test_lost_response_reconciles_without_republication_even_if_source_changed(self):
        self.graph.lose_response = True
        with self.assertRaises(TimeoutError): self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')
        self.source.revision = 'two'
        result = self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')
        self.assertEqual(result['status'], 'published')
        self.assertEqual(len(self.graph.calls), 1)

    def test_completed_retry_is_idempotent(self):
        first = self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')
        self.assertEqual(first, self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer'))
        self.assertEqual(len(self.graph.calls), 1)

    def test_tampered_preview_denied(self):
        self.store.values[self.preview['job_id']]['candidates'][0]['confidence'] = 1
        with self.assertRaises(BridgeConflict): self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')

    def test_concurrent_publication_denied(self):
        @contextmanager
        def busy(_): yield False
        self.store.advisory_lock = busy
        with self.assertRaises(BridgeConflict): self.jobs.publish(self.preview['job_id'], self.ids, 'reviewer')


class BridgeRouteTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.agentic_service import bridge_router
        self.routes = bridge_router
        self.jobs = BridgeJobs(InMemoryRegistry(), Source(), Graph())
        self.patch = patch.object(bridge_router, 'jobs', self.jobs); self.patch.start()
        self.env = patch.dict(os.environ, {'AUTH_MODE':'token','GRAPH_READ_TOKEN':'read-secret','AGENTIC_APPROVAL_TOKEN':'approve-secret'}); self.env.start()
        app = FastAPI(); app.include_router(bridge_router.router); self.client = TestClient(app)
    def tearDown(self): self.patch.stop(); self.env.stop()

    def test_preview_requires_reader(self):
        payload = {'ontology_id':'ontology','import_task_id':'import'}
        self.assertEqual(self.client.post('/api/v1/workflows/bridge/previews', json=payload).status_code, 403)
        response = self.client.post('/api/v1/workflows/bridge/previews', json=payload, headers={'Authorization':'Bearer read-secret'})
        self.assertEqual(response.status_code, 201)

    def test_publish_requires_approval_not_read_token(self):
        preview = self.jobs.preview('ontology','import','reader')
        path = f"/api/v1/workflows/bridge/previews/{preview['job_id']}/publish"
        payload = {'approved_candidate_ids':[preview['candidates'][0]['candidate_id']]}
        self.assertEqual(self.client.post(path, json=payload, headers={'Authorization':'Bearer read-secret'}).status_code, 403)
        payload.update(approved_by='reviewer', approval_token='approve-secret')
        self.assertEqual(self.client.post(path, json=payload).status_code, 200)
        artifact = self.client.get(f"/api/v1/workflows/bridge/jobs/{preview['publication_job_id']}/artifact", headers={'Authorization':'Bearer read-secret'})
        self.assertEqual(artifact.status_code, 200)
        self.assertNotIn('approve-secret', artifact.text)

    def test_legacy_artifact_traversal_and_read_auth(self):
        path = '/api/v1/workflows/artifacts/unknown/reports/missing.json'
        self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.get(path, headers={'Authorization':'Bearer read-secret'}).status_code, 404)


class GraphBridgeRouteTests(unittest.TestCase):
    def test_graph_client_uses_mounted_api_prefix(self):
        from unittest.mock import MagicMock
        from backend.agentic_service.bridge_jobs import GraphBridgeClient
        for base in ('http://graph:8013', 'http://graph:8013/api/v1'):
            with self.subTest(base=base), patch.dict(os.environ, {'GRAPH_SERVICE_URL': base, 'GRAPH_PUBLICATION_TOKEN': 'private-test'}), patch('httpx.Client') as client:
                response = MagicMock(); response.status_code = 200
                response.json.return_value = {'publication_id': 'job'}
                request = client.return_value.__enter__.return_value.request
                request.return_value = response
                GraphBridgeClient().receipt('job')
                self.assertEqual(request.call_args.args[:2], ('GET', 'http://graph:8013/api/v1/graph/bridge/publications/job'))

    def test_graph_client_does_not_hide_a_missing_publication_route(self):
        from unittest.mock import MagicMock
        from backend.agentic_service.bridge_jobs import GraphBridgeClient
        with patch.dict(os.environ, {'GRAPH_SERVICE_URL': 'http://graph:8013', 'GRAPH_PUBLICATION_TOKEN': 'private-test'}), patch('httpx.Client') as client:
            response = MagicMock(); response.status_code = 404
            response.raise_for_status.side_effect = RuntimeError('route missing')
            client.return_value.__enter__.return_value.request.return_value = response
            with self.assertRaises(Exception):
                GraphBridgeClient().publish({'publication_id': 'job'})
            response.raise_for_status.assert_called_once()

    def test_private_graph_routes_require_service_token(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.graph_service.bridge_router import router
        app = FastAPI(); app.include_router(router)
        with patch.dict(os.environ, {'GRAPH_PUBLICATION_TOKEN': 'private-test'}):
            client = TestClient(app)
            self.assertEqual(client.post('/graph/bridge/publications', json={}).status_code, 403)
            self.assertEqual(client.get('/graph/bridge/publications/job').status_code, 403)
            with patch('backend.graph_service.bridge_publication.receipt', return_value={'publication_id': 'job'}):
                response = client.get('/graph/bridge/publications/job', headers={'Authorization': 'Bearer private-test'})
                self.assertEqual(response.status_code, 200)

    def test_receipt_not_written_when_publication_count_changes(self):
        from unittest.mock import MagicMock
        from backend.graph_service.bridge_publication import _publish_transaction
        tx = MagicMock()
        state = MagicMock(); state.single.return_value = {'receipt': None}
        counts = MagicMock(); counts.data.return_value = [{'candidate_id': 'one', 'sources': 1, 'targets': 1}]
        writes = MagicMock(); writes.single.return_value = {'applied': 0}
        tx.run.side_effect = [state, counts, writes]
        with self.assertRaises(ValueError):
            _publish_transaction(tx, {'publication_id': 'job', 'rows': [{}], 'approved_by': 'reviewer'})
        self.assertEqual(tx.run.call_count, 3)


if __name__ == '__main__': unittest.main()
