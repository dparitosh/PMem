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

    def test_prompt_snapshot_is_retained_with_owner_access(self):
        self.proposal['prompt_details'] = {'system_prompt': 'Review only', 'user_request': 'Inspect ontology', 'prompt_version': 'v2'}
        saved = self.records.create(self.proposal, 'owner')
        self.proposal['prompt_details']['system_prompt'] = 'changed later'
        restored = self.records.get(saved['recommendation_id'], 'owner')
        self.assertEqual(restored['prompt_details']['system_prompt'], 'Review only')

    def test_context_and_snapshot_credentials_are_redacted_before_storage(self):
        self.proposal['context'] = {'api_key':'private-context'}
        self.proposal['prompt_details'] = {'user_request':'Bearer private.jwt'}
        saved = self.records.create(self.proposal,'owner')
        raw = self.records.store.get(saved['recommendation_id'])
        self.assertNotIn('private-context',str(raw))
        self.assertNotIn('private.jwt',str(raw))
