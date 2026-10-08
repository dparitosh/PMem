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
from rdflib import Graph

TTL = b'@prefix ex: <http://example/> . ex:Part a <http://www.w3.org/2002/07/owl#Class> .'


class RdfPublicationTests(unittest.TestCase):
    def test_normalization_retains_source_and_rejects_external_entities(self):
        with tempfile.TemporaryDirectory() as root, patch.object(rdf_conversion, 'ArtifactStore', lambda: ArtifactStore(Path(root))):
            result = rdf_conversion.convert_rdf(filename='demo.owl', content=TTL)
            self.assertEqual(len(Graph().parse(data=result['ontology']['turtle'], format='turtle')), 1)
            self.assertTrue(result['artifacts']['source'].startswith('sha256:'))
            with self.assertRaises(ValueError):
                rdf_conversion.convert_rdf(filename='demo.rdf', content=b'<!DOCTYPE rdf [<!ENTITY x SYSTEM "file:///secret">]><rdf/>')

    def test_rdf_publish_uses_governance_and_proxy_safe_transport(self):
        tree = ast.parse(Path('backend/ingestion_service/engineering_workflow.py').read_text(encoding='utf-8'))
        nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        calls, options = [], {}
        invalid_receipt = False
        class Response:
            def __init__(self, data): self.data = data
            def raise_for_status(self): pass
            def json(self): return self.data
        class Client:
            def __init__(self, **kwargs): options.update(kwargs)
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, url): return Response({'lifecycle_status': 'draft'})
            async def post(self, url, **kwargs):
                calls.append((url, kwargs))
                if url.endswith('/evaluate'): return Response({'compliant': True})
                if url.endswith('/quality-gate'): return Response({'publish_recommended': True})
                if url.endswith('/register'): return Response({'ontology_id': 'demo'})
                return Response({'status': 'success', 'ontology_id': 'wrong' if invalid_receipt else kwargs['data']['ontology_id'],
                                 'publication_id': kwargs['data']['publication_id']})
        async def thread(function, *args, **kwargs): return function(*args, **kwargs)
        namespace = {'__package__': 'backend.ingestion_service', 'Any': object, 'EngineeringSchemaConverter': object,
                     'asyncio': asyncio, 'os': os, 'hashlib': hashlib, 'json': json,
                     'httpx': SimpleNamespace(AsyncClient=Client), 'run_in_threadpool': thread,
                     'service_bearer_headers': lambda *args, **kwargs: {}}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<workflow>', 'exec'), namespace)
        workflow = namespace['EngineeringWorkflow'].__new__(namespace['EngineeringWorkflow'])
        workflow.timeout = 30; workflow.ontology_url = 'http://ontology/api/v1'; workflow.graph_url = 'http://graph/api/v1'
        with tempfile.TemporaryDirectory() as root, patch.object(rdf_conversion, 'ArtifactStore', lambda: ArtifactStore(Path(root))):
            result = asyncio.run(workflow.run(filename='demo.owl', content=TTL, publish=True))
            invalid_receipt = True
            with self.assertRaisesRegex(RuntimeError, 'receipt identity'):
                asyncio.run(workflow.run(filename='demo.owl', content=TTL, publish=True))
        self.assertEqual(result['status'], 'published')
        self.assertFalse(options['trust_env'])
        self.assertTrue(calls[0][0].endswith('/policies/evaluate'))
        self.assertTrue(calls[-1][0].endswith('/graph/ontologies/publish'))
        self.assertEqual(calls[-1][1]['data']['ontology_id'], 'demo')
