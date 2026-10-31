"""Version selection, TRS gaps and checkpoint failure regression tests."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch, MagicMock

from backend.artifact_store import ArtifactStore
from backend.mesh_store import InMemoryRegistry
from backend.data_pipeline_service import semantic_configuration as configurations


class ConfigurationTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.artifacts = ArtifactStore(Path(self.temporary.name))
        artifact = self.artifacts.ingest_bytes(b'<urn:part> <urn:name> "Part" .', filename='parts.ttl')
        self.selection = {'role':'source', 'source_id':'catalog:parts:1.0.0', 'artifact_id':artifact['artifact_id']}
        self.baselines = InMemoryRegistry()
        self.reviews = InMemoryRegistry()
        self.start_patch(patch.object(configurations, 'configuration_store', return_value=self.baselines))
        self.start_patch(patch.object(configurations, 'ArtifactStore', return_value=self.artifacts))
        self.resolve = self.start_patch(patch('backend.data_pipeline_service.semantic_datasets.resolve_source', return_value={'version':'1.0.0','revision':1}))
        self.baseline = configurations.freeze_configuration([self.selection], 'author')
        self.dataset = 'a' * 64
        db = MagicMock()
        db.cursor.return_value.__enter__.return_value.fetchone.return_value = ({'configuration_id':self.baseline['configuration_id']},)
        @contextmanager
        def connection():
            yield db
        self.reviews._connect = connection
        self.start_patch(patch.object(configurations,'PostgresRegistry',return_value=self.reviews))
        self.start_patch(patch.object(configurations,'notify_configuration'))
        self.start_patch(patch('backend.Services.oslc_trs_service.OSLCTRSService.is_enabled',return_value=True))
        self.changes = self.start_patch(patch('backend.Services.oslc_trs_service.OSLCTRSService.change_log',return_value={'events':[],'next_after':0,'rebase_required':False,'head_order':0}))

    def start_patch(self, item):
        value=item.start(); self.addCleanup(item.stop); return value

    def test_baseline_is_immutable_idempotent_and_does_not_approve(self):
        same=configurations.freeze_configuration([self.selection], 'another-author')
        self.assertEqual(same,self.baseline)
        self.assertEqual(same['approval_status'],'not_granted')
        self.resolve.return_value={'version':'1.0.0','revision':2}
        newer=configurations.freeze_configuration([self.selection])
        self.assertNotEqual(newer['configuration_id'],same['configuration_id'])
        pinned, source, shapes=configurations.preparation_configuration({**self.selection,'configuration_id':same['configuration_id']})
        self.assertEqual(source['source_version']['revision'],1)
        self.assertEqual(pinned,same)

    def test_changed_revision_requires_refresh_without_touching_publication(self):
        self.resolve.return_value={'version':'1.0.0','revision':2}
        result=configurations.review_dataset(self.dataset)
        self.assertEqual(result['status'],'refresh_required')
        self.assertFalse(result['publication_changed'])
        self.resolve.return_value={'version':'1.0.0','revision':1}
        self.assertEqual(configurations.review_dataset(self.dataset)['status'],'refresh_required')

    def test_trs_event_is_retained_with_checkpoint_and_deletion_is_not_replayed(self):
        self.changes.return_value={'events':[{'resource_uri':'https://host/oslc/lifecycle/products/parts%3A1.0.0','event_type':'Deletion','order':4}], 'next_after':4,'rebase_required':False,'head_order':4}
        result=configurations.review_dataset(self.dataset)
        self.assertEqual(result['status'],'refresh_required')
        self.assertEqual(self.reviews.get(self.dataset)['trs_after'],4)
        self.assertEqual(result['findings'][0]['event_type'],'Deletion')

    def test_gap_never_becomes_fresh_on_the_next_empty_page(self):
        self.changes.return_value={'events':[],'next_after':9,'rebase_required':True,'head_order':9}
        result=configurations.review_dataset(self.dataset)
        self.assertTrue(result['trs_gap_unresolved'])
        self.changes.return_value={'events':[],'next_after':9,'rebase_required':False,'head_order':9}
        self.assertEqual(configurations.review_dataset(self.dataset)['status'],'review_required')

    def test_lost_lease_cannot_advance_checkpoint(self):
        with patch.object(configurations,'ensure_execution_allowed',side_effect=[None,RuntimeError('Lease lost')]):
            with self.assertRaisesRegex(RuntimeError,'Lease lost'):
                configurations.review_dataset(self.dataset)
        self.assertIsNone(self.reviews.get(self.dataset))

    def test_configuration_does_not_allow_substituting_another_source(self):
        with self.assertRaisesRegex(ValueError,'differs'):
            configurations.preparation_configuration({**self.selection,'source_id':'catalog:other:1','configuration_id':self.baseline['configuration_id']})

    def test_context_header_rejects_foreign_origin_and_body_conflicts(self):
        identifier=self.baseline['configuration_id']
        path='/oslc/lifecycle/analytics-baselines/'+identifier
        with patch('backend.Services.oslc_trs_service.OSLCTRSService.base_url',return_value='https://local.example'):
            self.assertEqual(configurations.bind_context({},'https://local.example'+path,'rdf-semantic-materialize')['configuration_id'],identifier)
            with self.assertRaisesRegex(ValueError,'deployment'):
                configurations.bind_context({},'https://foreign.example'+path,'rdf-semantic-materialize')
            with self.assertRaisesRegex(ValueError,'disagree'):
                configurations.bind_context({'configuration_id':'b'*64},path,'rdf-semantic-materialize')

    def test_restored_trs_counter_cannot_certify_old_checkpoint_as_current(self):
        self.reviews.put(self.dataset,{'trs_after':50})
        self.changes.return_value={'events':[],'next_after':50,'rebase_required':False,'head_order':2}
        result=configurations.review_dataset(self.dataset)
        self.assertTrue(result['trs_gap_unresolved'])
        self.assertEqual(result['status'],'review_required')
