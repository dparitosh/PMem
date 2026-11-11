import copy
import hashlib
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock

from backend.mesh_store import InMemoryRegistry
from backend.ontology_service.merge_background import BackgroundMerges, validation_child, child_result_limit
from backend.tests.test_merge_entity_changes import MergeEntityChangesTests


class BackgroundMergeTests(unittest.TestCase):
    def setUp(self):
        self.jobs, self.previews = InMemoryRegistry(), InMemoryRegistry()
        self.worker = BackgroundMerges()
        self.worker.registry = lambda service: self.jobs
        self.service = SimpleNamespace(registry=self.previews, catalog=SimpleNamespace(
            get=lambda key: {'ontology_id': key}, read_artifact=lambda key: ({'ontology_name': key}, b'source')))
        self.payload = {'background': True, 'source_ontology_ids': ['a', 'b']}
        self.record = {'preview_id': 'temporary', 'turtle': 'graph', 'sources': [
            {'ontology_id': key, 'artifact_sha256': hashlib.sha256(b'source').hexdigest()} for key in ('a','b')],
            'source_ontology_ids': ['a','b'], 'entity_suggestions': [{'source_iri':'a', 'target_iri':'b'}],
            'conflicts': [], 'validation': {}, 'changes': {'entity_mappings': []}, 'semantic_checks': {'shacl_conforms': None}}

    def test_enqueue_does_not_parse_or_reason_and_status_hides_internal_payload(self):
        with patch('backend.ontology_service.merge_preparation.prepare') as prepare:
            result = self.worker.enqueue(self.service, self.payload)
        prepare.assert_not_called()
        self.assertEqual(result['job_status'], 'queued')
        self.assertNotIn('payload', result)
        self.assertFalse(result['publish_recommended'])

    def test_prepared_mappings_visible_while_validation_blocks_approval(self):
        key = self.worker.enqueue(self.service, self.payload)['preview_id']
        def validate(*args):
            status = self.worker.status(self.service, key)
            self.assertEqual(status['job_status'], 'validating')
            self.assertTrue(status['entity_suggestions'])
            self.assertNotIn('turtle', status)
            self.assertFalse(status['publish_recommended'])
            return {'shacl_conforms':True, 'inferred_conflicts':[], 'shape_digests':[], 'owl_rl_performed':True}
        with patch('backend.ontology_service.merge_preparation.prepare', return_value=copy.deepcopy(self.record)), \
             patch('backend.ontology_service.merge_semantics.validation_fingerprint', return_value='policy'), \
             patch('backend.ontology_service.merge_background.validation_child', side_effect=validate):
            self.worker.run_once(self.service, threading.Event())
        status = self.worker.status(self.service, key)
        self.assertEqual(status['job_status'], 'completed')
        self.assertTrue(status['publish_recommended'])
        self.assertNotIn('validation_receipt', status)

    def test_restart_reuses_prepared_plan(self):
        key = self.worker.enqueue(self.service, self.payload)['preview_id']
        self.previews.put(key, {**copy.deepcopy(self.record), 'preview_id':key, 'background_validation':True})
        with patch('backend.ontology_service.merge_preparation.prepare') as prepare, \
             patch('backend.ontology_service.merge_semantics.validation_fingerprint', return_value='policy'), \
             patch('backend.ontology_service.merge_background.validation_child', side_effect=InterruptedError):
            self.worker.run_once(self.service, threading.Event())
        prepare.assert_not_called()
        self.assertEqual(self.jobs.get(key)['status'], 'queued')
        self.assertIsNotNone(self.previews.get(key))

    def test_source_changed_cannot_validate_or_publish(self):
        key = self.worker.enqueue(self.service, self.payload)['preview_id']
        record = copy.deepcopy(self.record); record['sources'][0]['artifact_sha256'] = 'changed'
        self.previews.put(key, record)
        with patch('backend.ontology_service.merge_background.validation_child') as child:
            self.worker.run_once(self.service, threading.Event())
        child.assert_not_called()
        self.assertEqual(self.jobs.get(key)['status'], 'failed')
        self.assertFalse(self.worker.status(self.service, key)['publish_recommended'])

    def test_receipt_token_must_match_current_job(self):
        key = self.worker.enqueue(self.service, self.payload)['preview_id']
        self.jobs.put(key, {**self.jobs.get(key), 'status':'completed', 'token':'new'})
        with patch('backend.mesh_store.PostgresRegistry', return_value=self.jobs):
            self.assertFalse(self.worker.is_complete({'preview_id':key, 'validation_receipt':{'token':'old'}}))

    def test_pending_apply_rejected_before_register(self):
        service = MergeEntityChangesTests().service()
        records = {}
        service._load = lambda: records
        service._save = lambda values, key: records.update(values)
        result = service._preview({'source_ontology_ids':['a','b']}, defer_semantics=True)
        record = records[result['preview_id']]; record['background_validation'] = True
        service.catalog.register = Mock()
        with patch('backend.ontology_service.merge_background.background_merges.is_complete', return_value=False):
            with self.assertRaisesRegex(ValueError, 'not completed'): service._apply(result['preview_id'], 'reviewer')
        service.catalog.register.assert_not_called()

    def test_shutdown_terminates_only_owned_child(self):
        process = Mock(); process.poll.return_value = None
        stop = threading.Event(); stop.set()
        with patch('backend.ontology_service.merge_background.subprocess.Popen', return_value=process):
            with self.assertRaises(InterruptedError): validation_child((), stop, 1)
        process.kill.assert_called_once(); process.wait.assert_called_once()

    def test_graph_or_policy_tamper_rejected_before_catalog_write(self):
        for tamper in ('graph', 'policy'):
            with self.subTest(tamper=tamper):
                service = MergeEntityChangesTests().service()
                records = {}; service._load = lambda: records
                service._save = lambda values, key: records.update(values)
                preview = service._preview({'source_ontology_ids':['a','b']}, defer_semantics=True)
                record = records[preview['preview_id']]
                record.update(background_validation=True, validation_receipt={
                    'graph_sha256':hashlib.sha256(record['turtle'].encode()).hexdigest(), 'policy_sha256':'old'})
                if tamper == 'graph': record['turtle'] += '\n# changed'
                service.catalog.register = Mock()
                with patch('backend.ontology_service.merge_background.background_merges.is_complete', return_value=True), \
                     patch('backend.ontology_service.merge_semantics.validation_fingerprint', return_value='old' if tamper == 'graph' else 'new'):
                    with self.assertRaisesRegex(ValueError, 'policy/shapes changed'): service._apply(preview['preview_id'], 'reviewer')
                service.catalog.register.assert_not_called()

    def test_real_validation_child_returns_shacl_and_reasoning_evidence(self):
        evidence = validation_child(('@prefix owl: <http://www.w3.org/2002/07/owl#> . <urn:Part> a owl:Class .', [], [], False),
                                    threading.Event(), 30)
        self.assertIs(type(evidence['shacl_conforms']), bool)
        self.assertTrue(evidence['owl_rl_performed'])
        self.assertTrue(evidence['shape_digests'])

    def test_timeout_terminates_owned_child(self):
        process = Mock(); process.poll.return_value = None
        with patch('backend.ontology_service.merge_background.subprocess.Popen', return_value=process):
            with self.assertRaisesRegex(ValueError, 'deadline'): validation_child((), threading.Event(), 0)
        process.kill.assert_called_once(); process.wait.assert_called_once()

    def test_prepared_graph_larger_than_validation_report_is_accepted(self):
        import pickle
        graph_result = {'record': {'turtle': 'x' * (9 * 1024 * 1024)}}
        encoded = pickle.dumps(graph_result)
        def worker(*args, **kwargs):
            kwargs['stdout'].write(encoded)
            process = Mock(); process.poll.return_value = 0; process.returncode = 0
            return process
        with patch('backend.ontology_service.merge_background.subprocess.Popen', side_effect=worker):
            actual = validation_child((), threading.Event(), 10, 'backend.ontology_service.merge_preparation')
            self.assertEqual(len(actual['record']['turtle']), 9 * 1024 * 1024)
            with self.assertRaisesRegex(ValueError, 'size limit'):
                validation_child((), threading.Event(), 10)
        self.assertGreater(child_result_limit('backend.ontology_service.merge_preparation'), len(encoded))
        with self.assertRaisesRegex(ValueError, 'Unsupported'): child_result_limit('arbitrary.module')
