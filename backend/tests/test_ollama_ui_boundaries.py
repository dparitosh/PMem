import ast
import asyncio
import importlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

class OllamaUiBoundaryTests(unittest.TestCase):
    def companion_fixture(self, payload):
        response = MagicMock()
        async def chunks():
            yield json.dumps(payload).encode()
        response.aiter_bytes = chunks
        stream = MagicMock(); stream.__aenter__ = AsyncMock(return_value=response); stream.__aexit__ = AsyncMock(return_value=False)
        client = MagicMock(); client.stream.return_value = stream
        context = MagicMock(); context.__aenter__ = AsyncMock(return_value=client); context.__aexit__ = AsyncMock(return_value=False)
        http = types.ModuleType('httpx'); http.HTTPError = type('HTTPError', (Exception,), {}); http.AsyncClient = MagicMock(return_value=context)
        with patch.dict(sys.modules, {'httpx':http}):
            scope={'__name__':'backend.agentic_service.companion','__package__':'backend.agentic_service'}
            exec(compile(Path('backend/agentic_service/companion.py').read_text(), 'companion', 'exec'),scope)
        return scope['KnowledgeCompanion'](), http

    def test_bounded_retrieval_uses_service_proxy_policy(self):
        companion, http = self.companion_fixture({'nodes': [], 'relationships': []})
        result = asyncio.run(companion.ask('product', headers={}))
        self.assertEqual(result['status'], 'no_evidence')
        self.assertFalse(http.AsyncClient.call_args.kwargs['trust_env'])

    def test_invalid_and_oversized_evidence_is_rejected(self):
        companion, _ = self.companion_fixture({'nodes': 'invalid', 'relationships': []})
        with self.assertRaisesRegex(RuntimeError, 'invalid evidence'):
            asyncio.run(companion.ask('product', headers={}))
        companion, _ = self.companion_fixture({'nodes': [], 'relationships': []})
        with patch.dict(os.environ, {'AGENTIC_MAX_RESPONSE_BYTES':'8'}), self.assertRaisesRegex(RuntimeError, 'retrieval is unavailable'):
            asyncio.run(companion.ask('product', headers={}))

    def test_ontology_model_failure_retains_deterministic_review(self):
        tree=ast.parse(Path('backend/agentic_service/ontology_orchestrator.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_llm_suggestion')
        scope={'os':os,'Any':object,'__name__':'backend.agentic_service.ontology_orchestrator','__package__':'backend.agentic_service'}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'suggestion','exec'),scope)
        local=types.ModuleType('backend.agentic_service.local_llm'); local.summarize=AsyncMock(side_effect=TimeoutError())
        with patch.dict(sys.modules,{'backend.agentic_service.local_llm':local}), patch.dict(os.environ,{'ONTOLOGY_AGENT_LLM_ENABLED':'true'}):
            result=scope['_llm_suggestion']({'matched':1},{'source':'parts'})
        self.assertEqual(result['status'],'unavailable')
        local.summarize.assert_awaited_once()
