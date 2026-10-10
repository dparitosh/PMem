import ast
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from backend.agentic_service.prompt_limits import bounded_prompt_json


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
            return {'done': True, 'message': {'content': 'Grounded summary [evidence:urn:Part]'}}
        async def on_token(text): tokens.append(text)
        namespace = {'os': os, 'asyncio': asyncio, 'httpx': SimpleNamespace(AsyncClient=Client),
                     'settings': lambda: ('ollama', 'llama3:latest', 'http://host/ollama', 30, {}),
                     'bounded_prompt_json': bounded_prompt_json,
                     '_post_json': post, '_content': lambda result, operation: result['message']['content']}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<companion>', 'exec'), namespace)
        with patch.dict(os.environ, {'OLLAMA_BASE_URL': 'http://host/ollama', 'OLLAMA_API_URL': '',
                                     'OLLAMA_STREAMING_ENABLED': 'false'}):
            result = asyncio.run(namespace['summarize']('Part', [{'label': 'Part', 'iri':'urn:Part'}], on_token=on_token))
        self.assertFalse(observed['stream'])
        self.assertEqual(result, 'Grounded summary [evidence:urn:Part]')
        self.assertEqual(tokens, ['Grounded summary [evidence:urn:Part]'])
        async def long_post(*args):
            return {'done': True, 'message': {'content': '[evidence:urn:Part] ' + 'x' * 4001}}
        namespace['_post_json'] = long_post
        details = {}
        tokens.clear()
        with patch.dict(os.environ, {'OLLAMA_BASE_URL': 'http://host/ollama', 'OLLAMA_API_URL': '',
                                     'OLLAMA_STREAMING_ENABLED': 'false'}):
            result = asyncio.run(namespace['summarize']('Part', [{'iri':'urn:Part'}], on_token=on_token, prompt_details=details))
        self.assertTrue(details['output_truncated'])
        self.assertIn('Summary truncated', result)
        self.assertEqual(tokens, [result])


    def test_streamed_summary_is_not_emitted_until_citations_pass(self):
        from contextlib import asynccontextmanager
        node = next(node for node in ast.parse(Path('backend/agentic_service/local_llm.py').read_text(encoding='utf-8')).body if isinstance(node,ast.AsyncFunctionDef) and node.name=='summarize')
        tokens = []
        response = SimpleNamespace(raise_for_status=lambda:None)
        class Client:
            def __init__(self,**kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            @asynccontextmanager
            async def stream(self,*args,**kwargs): yield response
        async def frames(response):
            yield {'message':{'content':'Part '},'done':False}
            if tokens: raise AssertionError('Unvalidated model text escaped')
            yield {'message':{'content':'[evidence:urn:Part]'},'done':True}
        async def emit(text): tokens.append(text)
        namespace = {'os':os,'asyncio':asyncio,'httpx':SimpleNamespace(AsyncClient=Client),
                     'settings':lambda:('ollama','fixture','http://host',30,{}),
                     'bounded_prompt_json':bounded_prompt_json,'_stream_frames':frames,
                     '_content':lambda result,operation:result['message']['content']}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<summary-stream>','exec'),namespace)
        with patch.dict(os.environ,{'OLLAMA_BASE_URL':'http://host','OLLAMA_API_URL':'','OLLAMA_STREAMING_ENABLED':'true'}):
            result = asyncio.run(namespace['summarize']('Part',[{'iri':'urn:Part'}],on_token=emit))
        self.assertEqual(tokens,[result])
        tokens.clear()
        async def invalid_frames(response):
            yield {'message':{'content':'Invented [evidence:unknown]'},'done':True}
        namespace['_stream_frames'] = invalid_frames
        with patch.dict(os.environ,{'OLLAMA_BASE_URL':'http://host','OLLAMA_API_URL':'','OLLAMA_STREAMING_ENABLED':'true'}):
            with self.assertRaisesRegex(ValueError,'citations'):
                asyncio.run(namespace['summarize']('Part',[{'iri':'urn:Part'}],on_token=emit))
        self.assertEqual(tokens,[])
