import unittest
from backend.agentic_service.recommendations import RecommendationStore
from backend.mesh_store import InMemoryRegistry

class RecommendationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.records = RecommendationStore(InMemoryRegistry())
        self.proposal = {'command': {'agent_id':'ontology-governor','tool_id':'bridge.mapping.preview','inputs':{'ontology_id':'parts'}}, 'requires_approval':True}

    def test_saved_recommendation_is_isolated_and_reloadable_by_its_owner(self):
        saved = self.records.create(self.proposal, 'owner')
        identifier = saved['recommendation_id']
        saved['command']['inputs']['ontology_id'] = 'tampered'
        restored = self.records.get(identifier, 'owner')
        self.assertEqual(restored['command']['inputs']['ontology_id'], 'parts')
        self.assertNotIn('owner', restored)
        with self.assertRaises(PermissionError): self.records.get(identifier, 'other')
        with self.assertRaises(KeyError): self.records.get('missing', 'owner')

    def test_credentials_are_not_saved_in_model_recommendations(self):
        self.proposal['command']['inputs']['nested'] = {'approval_token':'private'}
        with self.assertRaisesRegex(ValueError, 'credentials'):
            self.records.create(self.proposal, 'owner')
        self.assertEqual(self.records.store.all(), {})
