import ast
import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch

class OllamaHealthFlags(unittest.TestCase):
    def test_failed_discovery_preserves_configured_enablement(self):
        tree = ast.parse(Path('backend/agentic_service/local_llm.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'health')
        async def probe(): return {'status':'route_missing', 'http_status':404}
        ns = {'os':os, '_health':probe}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual health>','exec'),ns)
        with patch.dict(os.environ, {'ONTOLOGY_AGENT_LLM_ENABLED':'true', 'COMPANION_LLM_ENABLED':'true'}):
            result = asyncio.run(ns['health']())
        self.assertEqual(result['status'],'route_missing')
        self.assertTrue(result['ontology_agent_enabled'])
        self.assertTrue(result['companion_enabled'])
        with patch.dict(os.environ, {'ONTOLOGY_AGENT_LLM_ENABLED':'false', 'COMPANION_LLM_ENABLED':'false'}):
            result = asyncio.run(ns['health']())
        self.assertFalse(result['ontology_agent_enabled'])
        self.assertFalse(result['companion_enabled'])

class OllamaGenerationContract(unittest.TestCase):
    def test_companion_uses_native_generate_body_and_response(self):
        from types import SimpleNamespace
        from backend.core.ollama_auth import ollama_headers
        tree = ast.parse(Path('backend/agentic_service/local_llm.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'summarize')
        observed = {}
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, endpoint, **kwargs):
                observed.update(endpoint=endpoint, **kwargs)
                return SimpleNamespace(raise_for_status=lambda:None, json=lambda:{'response':'Evidence summary'})
        ns = {'asyncio':asyncio, 'httpx':SimpleNamespace(AsyncClient=Client),
              'settings':lambda:('ollama','llama3:latest','http://custom.azure-api.net/ollama',30,{'api-key':'fixture'})}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual summary>','exec'),ns)
        with patch.dict(os.environ, {'OLLAMA_API_URL':'http://custom.azure-api.net/ollama/api/generate'}, clear=True):
            result = asyncio.run(ns['summarize']('question',{'source':'evidence'}))
        self.assertEqual(result,'Evidence summary')
        self.assertTrue(observed['endpoint'].endswith('/api/generate'))
        self.assertEqual(observed['headers'],{'api-key':'fixture'})
        self.assertIn('prompt',observed['json'])
        self.assertIn('system',observed['json'])
        self.assertNotIn('messages',observed['json'])
        self.assertEqual(observed['json']['model'],'llama3:latest')

if __name__ == '__main__': unittest.main()
