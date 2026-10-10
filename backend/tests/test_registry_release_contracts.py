import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from backend.agentic_service.catalog_contract import validate_catalog
from backend.agentic_service.catalog_loader import load_catalog
from backend.agentic_service.agent_usage import describe
from backend.data_catalog_service.product_contract import validate_registration, public_record
from backend.depo_platform.service_catalog import service_rows
from backend.data_product_service.storage import product_storage_root

ROOT = Path(__file__).resolve().parents[2]


class RegistryReleaseContracts(unittest.TestCase):
    def test_actual_agents_share_discovery_source(self):
        catalog = load_catalog()
        self.assertEqual({row['id'] for row in describe(catalog)}, {agent['id'] for agent in catalog['agents']})

    def test_duplicate_and_broken_workflow_identities_rejected(self):
        source = load_catalog()
        bad = copy.deepcopy(source); bad['agents'].append(copy.deepcopy(bad['agents'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'): validate_catalog(bad)
        bad = copy.deepcopy(source); bad['workflows'][0]['steps'][0]['agent_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'binding'): validate_catalog(bad)
        bad = copy.deepcopy(source); bad['workflows'][0]['steps'][0]['agent_id'] = []
        with self.assertRaises(ValueError): validate_catalog(bad)

    def test_catalog_rejects_nested_credentials_and_redacts_legacy(self):
        payload = dict(name='A',domain='engineering',owner='owner',classification='internal',steward='steward',lifecycle_state='draft')
        for key in ('password', 'Authorization', 'Ocp-Apim-Subscription-Key', 'api_key'):
            bad = {**payload, 'sources': [{'nested': {key:'private'}}]}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'credentials'): validate_registration(bad)
            exposed = public_record({**bad, 'unknown_private_field':'private'})
            self.assertNotIn('private', json.dumps(exposed))
        validate_registration(payload)

    def test_local_gateway_and_explicit_routes(self):
        manifest = json.loads((ROOT/'infra/deployment/services.json').read_text())
        with patch.dict(os.environ, {'DEPO_ROUTING_MODE':'local','DEPO_LOCAL_SERVICE_HOST':'10.0.2.16'}):
            rows = service_rows(manifest)
            self.assertEqual(rows[3]['endpoint'], 'http://10.0.2.16:8013')
        with patch.dict(os.environ, {'DEPO_ROUTING_MODE':'gateway','DEPO_API_GATEWAY_URL':'https://gateway.test/depo','DEPO_GATEWAY_GRAPH_PATH':'engineering/graph'}):
            rows = service_rows(manifest)
            self.assertEqual(rows[3]['health_endpoint'], 'https://gateway.test/depo/engineering/graph/readyz')
        with patch.dict(os.environ, {'DEPO_ROUTING_MODE':'','GRAPH_SERVICE_URL':'http://graph.test:8013/api/v1'}):
            self.assertEqual(service_rows(manifest)[3]['endpoint'], 'http://graph.test:8013')

    def test_secret_service_url_rejected(self):
        manifest = json.loads((ROOT/'infra/deployment/services.json').read_text())
        with patch.dict(os.environ, {'DEPO_ROUTING_MODE':'gateway','DEPO_API_GATEWAY_URL':'http://user:secret@gateway.test'}):
            with self.assertRaises(ValueError): service_rows(manifest)

    def test_durable_storage_and_explicit_legacy_override(self):
        with patch.dict(os.environ, {'ARTIFACT_STORAGE':'/durable/artifacts','DATA_PRODUCT_STORAGE':''}):
            self.assertEqual(product_storage_root(), Path('/durable/artifacts/products'))
        with patch.dict(os.environ, {'ARTIFACT_STORAGE':'/durable/artifacts','DATA_PRODUCT_STORAGE':'/existing/packages'}):
            self.assertEqual(product_storage_root(), Path('/existing/packages'))
