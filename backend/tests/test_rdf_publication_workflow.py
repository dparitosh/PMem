import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.artifact_store import ArtifactStore
from backend.ingestion_service import rdf_conversion
from backend.ingestion_service import engineering_workflow
from rdflib import Graph

TTL = b'@prefix ex: <http://example/> . ex:Part a <http://www.w3.org/2002/07/owl#Class> .'


class RdfPublicationTests(unittest.TestCase):
    def test_normalization_retains_source_and_rejects_external_entities(self):
        with tempfile.TemporaryDirectory() as root, patch.object(rdf_conversion, 'ArtifactStore', lambda: ArtifactStore(Path(root))):
            result = rdf_conversion.convert_rdf(filename='demo.owl', content=TTL)
            self.assertEqual(len(Graph().parse(data=result['ontology']['turtle'], format='turtle')), 1)
            self.assertTrue(result['artifacts']['source'].startswith('sha256:'))
            draft = result['data_product_draft']
            self.assertEqual(draft['product_kind'], 'ontology-evidence')
            self.assertEqual(draft['quality_status'], 'requires_review')
            self.assertEqual({item['artifact_id'] for item in draft['artifacts']}, set(result['artifacts'].values()))
            for item in draft['artifacts']:
                metadata, path = ArtifactStore(Path(root)).resolve(item['artifact_id'])
                self.assertTrue(path.is_file())
            with self.assertRaises(ValueError):
                rdf_conversion.convert_rdf(filename='demo.rdf', content=b'<!DOCTYPE rdf [<!ENTITY x SYSTEM "file:///secret">]><rdf/>')

    def test_rdf_publish_uses_governance_and_proxy_safe_transport(self):
        calls, options = [], {}
        invalid_receipt = False
        invalid_counts = False
        lifecycle = 'draft'
        class Response:
            status_code = 200
            def __init__(self, data): self.data = data
            def raise_for_status(self): pass
            def json(self): return self.data
        class Client:
            def __init__(self, **kwargs): options.update(kwargs)
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, url, **kwargs): return Response({'lifecycle_status': lifecycle})
            async def post(self, url, **kwargs):
                calls.append((url, kwargs))
                if url.endswith('/evaluate'): return Response({'compliant': True})
                if url.endswith('/quality-gate'): return Response({'publish_recommended': True})
                if url.endswith('/register'): return Response({'ontology_id': 'demo'})
                return Response({'status':'published','ontology_id':'demo','publication_id':'digest',
                    'receipt': {'status':'published','ontology_id':'wrong' if invalid_receipt else 'demo',
                                'publication_id':'digest','resources':-1 if invalid_counts else 1,'relationships':0}})
        async def thread(function, *args, **kwargs): return function(*args, **kwargs)
        workflow = engineering_workflow.EngineeringWorkflow.__new__(engineering_workflow.EngineeringWorkflow)
        workflow.timeout = 30; workflow.ontology_url = 'http://ontology/api/v1'; workflow.graph_url = 'http://graph/api/v1'
        with tempfile.TemporaryDirectory() as root, patch.object(rdf_conversion, 'ArtifactStore', lambda: ArtifactStore(Path(root))), \
                patch.object(engineering_workflow.httpx,'AsyncClient',Client), \
                patch.object(engineering_workflow,'service_bearer_headers',lambda *args,**kwargs:{}):
            draft = asyncio.run(workflow.run(filename='demo.owl', content=TTL, publish=True))
            self.assertEqual(draft['status'],'approval_required')
            self.assertFalse(any(url.endswith('/publish') for url,_ in calls))
            lifecycle = 'approved'
            result = asyncio.run(workflow.run(filename='demo.owl', content=TTL, publish=True))
            invalid_receipt = True
            with self.assertRaisesRegex(RuntimeError, 'receipt identity'):
                asyncio.run(workflow.run(filename='demo.owl', content=TTL, publish=True))
            invalid_receipt = False
            invalid_counts = True
            with self.assertRaisesRegex(RuntimeError, 'receipt identity'):
                asyncio.run(workflow.run(filename='demo.owl', content=TTL, publish=True))
        self.assertEqual(result['status'], 'published')
        registration_call = next(kwargs for url, kwargs in calls if url.endswith('/register'))
        retained_metadata = json.loads(registration_call['data']['extra_metadata'])
        self.assertEqual(retained_metadata['data_product_draft']['product_kind'], 'ontology-evidence')
        self.assertEqual(retained_metadata['data_product_draft']['quality_status'], 'requires_review')
        self.assertFalse(options['trust_env'])
        self.assertTrue(calls[0][0].endswith('/policies/evaluate'))
        self.assertTrue(calls[-1][0].endswith('/ontologies/demo/publish'))
        self.assertTrue(calls[-1][1]['params']['background'])
        self.assertFalse(any('/graph/' in url for url,_ in calls))
