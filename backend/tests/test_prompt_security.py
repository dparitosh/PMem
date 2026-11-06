import os
import unittest
from unittest.mock import patch
from backend.agentic_service.prompt_security import protect, prompt_identity, evidence_ids, validate_summary
from backend.agentic_service.prompt_policy import proposal_instructions
from backend.agentic_service.catalog_loader import load_catalog
from backend.agentic_service.catalog_contract import validate_catalog


class PromptSecurityTests(unittest.TestCase):
    def test_redacts_named_credentials_known_values_and_database_passwords(self):
        original = {'context': {'INGESTION_WRITE_TOKEN':'unknown-value'}, 'task':'Bearer private.jwt and ADMIN_API_KEY=other-secret', 'prompt_details':{'user_prompt':'Configured fixture-secret-value postgresql://user:dbsecret@host/depo'}}
        with patch.dict(os.environ, {'ADMIN_API_KEY':'fixture-secret-value'}):
            safe = protect(original)
        for value in ['unknown-value','private.jwt','other-secret','fixture-secret-value','dbsecret']:
            self.assertNotIn(value,str(safe))
        self.assertEqual(original['context']['INGESTION_WRITE_TOKEN'],'unknown-value')

    def test_prompt_hash_changes_with_policy(self):
        self.assertEqual(prompt_identity('a'),prompt_identity('a'))
        self.assertNotEqual(prompt_identity('a'),prompt_identity('b'))

    def test_citations_must_be_present_and_supplied(self):
        identifiers = evidence_ids({'nodes':[{'elementId':'node-1','properties':{'iri':'urn:Part'}}]})
        self.assertEqual(validate_summary('Part [evidence:urn:Part]',identifiers),'Part [evidence:urn:Part]')
        for answer in ['Part','Part [evidence:invented]']:
            with self.assertRaises(ValueError): validate_summary(answer,identifiers)

    def test_invalid_custom_prompt_rejected(self):
        for prompt in [42, '漢'*6000]:
            data = load_catalog()
            data['agents'][0]['system_prompt'] = prompt
            with self.assertRaisesRegex(ValueError,'prompt'): validate_catalog(data)
            with self.assertRaises(ValueError): proposal_instructions({'system_prompt':prompt},'native')

    def test_native_policy_requests_exactly_one_call(self):
        text = proposal_instructions({'id':'ontology-governor'},'native')
        self.assertIn('exactly one native tool call',text)
        self.assertNotIn('Return only its arguments',text)
