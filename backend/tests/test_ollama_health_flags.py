import ast
import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch

class OllamaHealthFlags(unittest.TestCase):
    def test_configuration_check_rejects_whitespace_model_before_transport(self):
        tree = ast.parse(Path('backend/agentic_service/local_llm.py').read_text())
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name in {'settings', '_health'}]
        ns = {'os': os}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual model check>', 'exec'), ns)
        with patch.dict(os.environ, {'LLM_MODEL_NAME': '   '}, clear=True):
            result = asyncio.run(ns['_health']())
        self.assertEqual(result['status'], 'invalid_configuration')
        self.assertIn('model name', result['action'])

    def test_configuration_check_preserves_exported_http_apim_endpoint(self):
        tree = ast.parse(Path('backend/agentic_service/local_llm.py').read_text())
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name in {'settings', '_health', 'health'}]
        ns = {'os': os}
        # No HTTP client is provided: configuration-only checks must not probe.
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual HTTP health>', 'exec'), ns)
        with patch.dict(os.environ, {
            'USE_LLM': 'ollama', 'LLM_MODEL_NAME': 'llama3:latest',
            'OLLAMA_API_URL': 'http://azdtapimanager.azure-api.net/ollama',
            'OLLAMA_API_KEY': 'fixture', 'OLLAMA_API_KEY_HEADER': 'api-key',
            'OLLAMA_DISCOVERY_ENABLED': 'false',
            'ONTOLOGY_AGENT_LLM_ENABLED': 'true', 'COMPANION_LLM_ENABLED': 'true',
        }, clear=True):
            self.assertEqual(ns['settings']()[4], {'api-key': 'fixture'})
            result = asyncio.run(ns['health']())
        self.assertEqual(result['status'], 'generation_unverified')
        self.assertEqual(result['endpoint'], 'http://azdtapimanager.azure-api.net/ollama/api/chat')
        self.assertTrue(result['ontology_agent_enabled'])
        self.assertTrue(result['companion_enabled'])
        self.assertNotIn('headers', result)
        self.assertNotIn('fixture', str(result))

    def test_apim_contract_without_discovery_does_not_call_tags(self):
        tree = ast.parse(Path('backend/agentic_service/local_llm.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_health')
        ns = {'os': os, 'settings': lambda: ('ollama', 'llama3:latest', 'https://gateway/ollama', 30, {})}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual probe>', 'exec'), ns)
        with patch.dict(os.environ, {'OLLAMA_DISCOVERY_ENABLED': 'false', 'OLLAMA_API_URL': 'https://gateway/ollama/api/generate'}, clear=True):
            result = asyncio.run(ns['_health']())
        self.assertEqual(result['status'], 'generation_unverified')
        self.assertEqual(result['endpoint'], 'https://gateway/ollama/api/generate')
        self.assertFalse(result['discovery_enabled'])
        self.assertNotIn('probe_timeout_seconds', result)

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
        reply = {'response': 'Evidence summary', 'done': True}
        async def post_json(client, endpoint, headers, body):
            observed.update(endpoint=endpoint, headers=headers, json=body)
            return reply
        ns = {'asyncio':asyncio, '_post_json':post_json, 'httpx':SimpleNamespace(AsyncClient=Client),
              'settings':lambda:('ollama','llama3:latest','http://custom.azure-api.net/ollama',30,{'api-key':'fixture'})}
        content = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_content')
        exec(compile(ast.Module(body=[content,node],type_ignores=[]),'<actual summary>','exec'),ns)
        with patch.dict(os.environ, {'OLLAMA_API_URL':'http://custom.azure-api.net/ollama/api/generate'}, clear=True):
            result = asyncio.run(ns['summarize']('question',{'source':'evidence'}))
        self.assertEqual(result,'Evidence summary')
        self.assertTrue(observed['endpoint'].endswith('/api/generate'))
        self.assertEqual(observed['headers'],{'api-key':'fixture'})
        self.assertIn('prompt',observed['json'])
        self.assertIn('system',observed['json'])
        self.assertNotIn('messages',observed['json'])
        self.assertEqual(observed['json']['model'],'llama3:latest')
        reply['done'] = False
        with patch.dict(os.environ, {'OLLAMA_API_URL':'http://custom.azure-api.net/ollama/api/generate'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'incomplete summary'):
                asyncio.run(ns['summarize']('question', {'source':'evidence'}))

if __name__ == '__main__': unittest.main()
