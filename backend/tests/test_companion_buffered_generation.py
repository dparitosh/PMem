import ast
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class BufferedCompanionTests(unittest.TestCase):
    def test_ui_callback_uses_non_streaming_gateway_and_receives_summary(self):
        node = next(node for node in ast.parse(Path('backend/agentic_service/local_llm.py').read_text(encoding='utf-8')).body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == 'summarize')
        observed, tokens = {}, []
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        async def post(client, endpoint, headers, body):
            observed.update(body)
            return {'done': True, 'message': {'content': 'Grounded summary'}}
        async def on_token(text): tokens.append(text)
        namespace = {'os': os, 'asyncio': asyncio, 'httpx': SimpleNamespace(AsyncClient=Client),
                     'settings': lambda: ('ollama', 'llama3:latest', 'http://host/ollama', 30, {}),
                     '_post_json': post, '_content': lambda result, operation: result['message']['content']}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<companion>', 'exec'), namespace)
        with patch.dict(os.environ, {'OLLAMA_BASE_URL': 'http://host/ollama', 'OLLAMA_API_URL': '',
                                     'OLLAMA_STREAMING_ENABLED': 'false'}):
            result = asyncio.run(namespace['summarize']('Part', [{'label': 'Part'}], on_token=on_token))
        self.assertFalse(observed['stream'])
        self.assertEqual(result, 'Grounded summary')
        self.assertEqual(tokens, ['Grounded summary'])
