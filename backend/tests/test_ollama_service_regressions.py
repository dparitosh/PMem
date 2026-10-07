import ast
import os
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from backend.core.ollama_auth import ollama_base_url, ollama_generation_route, ollama_timeout

class OllamaServiceRegressions(unittest.TestCase):
    def test_legacy_query_without_discovery_calls_generation(self):
        tree = ast.parse(Path('backend/main.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'ollama_query')
        node.decorator_list = []
        service = Mock()
        service.answer_question.return_value = {'answer': 'fixture'}
        class HttpError(Exception):
            def __init__(self, **kwargs): pass
        ns = {'OllamaQueryRequest': object, 'HTTPException': HttpError, 'get_ollama_service':lambda: service}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual legacy route>', 'exec'), ns)
        with patch.dict(os.environ, {'OLLAMA_DISCOVERY_ENABLED':'false'}, clear=True):
            result = ns['ollama_query'](types.SimpleNamespace(query='question'))
        self.assertEqual(result, {'answer':'fixture'})
        service.health_check.assert_not_called()
        service.answer_question.assert_called_once_with('question')

    def service(self, url='http://fixture/api/chat'):
        # Execute the actual service class with a controlled HTTP transport.
        tree = ast.parse(Path('backend/Services/ollama_service.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        session = Mock()
        requests = types.SimpleNamespace(Session=lambda: session, exceptions=types.SimpleNamespace(Timeout=TimeoutError))
        import logging
        from typing import Optional, Dict, Any
        from datetime import datetime
        ns = dict(os=os, requests=requests, logger=logging.getLogger('audit'), Optional=Optional, Dict=Dict, Any=Any,
                  datetime=datetime, ollama_base_url=ollama_base_url, ollama_generation_route=ollama_generation_route, ollama_timeout=ollama_timeout)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual service>', 'exec'), ns)
        return ns['OllamaService'](url, 'fixture', ''), session

    def test_chat_route_payload_and_timeout(self):
        with patch.dict(os.environ, {'LLM_REQUEST_TIMEOUT_SECONDS':'2'}, clear=True):
            service, session = self.service()
            session.post.return_value.json.return_value = {'message': {'content':'answer'}}
            self.assertEqual(service.query('question', temperature=0.2), 'answer')
            args, kw = session.post.call_args
            self.assertEqual(args[0], 'http://fixture/api/chat')
            self.assertEqual(kw['timeout'], 2)
            self.assertEqual(kw['json']['options']['temperature'], 0.2)
            self.assertFalse(session.trust_env)

    def test_generate_route(self):
        with patch.dict(os.environ, {}, clear=True):
            service, session = self.service('http://fixture/api/generate')
            session.post.return_value.json.return_value = {'response':'answer'}
            self.assertEqual(service.query('question'), 'answer')
            self.assertEqual(session.post.call_args.args[0], 'http://fixture/api/generate')

    def test_health_validates_model_and_body(self):
        service, session = self.service()
        session.get.return_value.status_code = 200
        for body in ({'message':{}}, {'models':[]}, {'models':[{'name':'another'}]}):
            session.get.return_value.json.return_value = body
            self.assertFalse(service.health_check())
        session.get.return_value.json.return_value = {'models':[{'name':'fixture:latest'}]}
        self.assertTrue(service.health_check())

    def test_failed_generation_raises(self):
        service, session = self.service()
        session.post.return_value.json.return_value = {'error':'missing model'}
        with self.assertRaises(RuntimeError): service.answer_question('question')

    def test_invalid_ports(self):
        for url in ('http://localhost:bad', 'http://localhost:65536', 'http://localhost:0'):
            with self.assertRaises(ValueError): ollama_base_url(url)

    def test_configuration_is_not_validated_at_import(self):
        tree = ast.parse(Path('backend/core/llm.py').read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'ollama_base_url' for n in ast.walk(node)))

if __name__ == '__main__': unittest.main()
