"""Provider contracts without paid inference or local model downloads."""
import asyncio
import json
import os
import unittest
from unittest.mock import patch
import httpx
from backend.core.llm_providers import cloud_settings, cloud_chat, cloud_embeddings, post_cloud_chat
from backend.agentic_service import local_llm

ENV = {'USE_LLM': 'openai', 'OPENAI_MODEL': 'fixture-chat', 'OPENAI_API_KEY': 'fixture-secret',
       'OPENAI_EMBED_MODEL': 'fixture-embed', 'MISTRAL_MODEL': 'fixture-mistral',
       'MISTRAL_API_KEY': 'mistral-secret', 'MISTRAL_EMBED_MODEL': 'mistral-embed'}


class ProviderSettingsTests(unittest.TestCase):
    def test_provider_names_do_not_reuse_ollama_models(self):
        with patch.dict(os.environ, {**ENV, 'LLM_MODEL_NAME': 'stale-local-model'}, clear=True):
            self.assertEqual(cloud_settings('openai').model, 'fixture-chat')
            self.assertEqual(cloud_settings('mistral', embeddings=True).model, 'mistral-embed')
            self.assertNotIn('fixture-secret', repr(cloud_settings('openai')))

    def test_required_credentials_and_models(self):
        for provider in ('openai', 'mistral'):
            with self.subTest(provider=provider), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError) as error:
                    cloud_settings(provider)
                self.assertIn(provider.upper()+'_API_KEY', str(error.exception))
                self.assertIn(provider.upper()+'_MODEL', str(error.exception))

    def test_unsafe_urls_and_header_injection_rejected_without_values(self):
        for value in ('http://api.example/v1', 'https://user:secret@host/v1', 'https://host/v1?q=secret', 'https://host/v1#secret', ''):
            with self.subTest(value=value), patch.dict(os.environ, {**ENV, 'OPENAI_BASE_URL': value}, clear=True):
                with self.assertRaises(ValueError) as error:
                    cloud_settings('openai')
                self.assertNotIn('secret', str(error.exception))
        with patch.dict(os.environ, {**ENV, 'OPENAI_API_KEY': 'secret\nheader'}, clear=True):
            with self.assertRaises(ValueError): cloud_settings('openai')

    def test_vision_model_is_explicit(self):
        with patch.dict(os.environ, ENV, clear=True):
            with self.assertRaisesRegex(ValueError, 'UNSTRUCTURED_OPENAI_MODEL'):
                cloud_settings('openai', unstructured=True)

    def test_installed_langchain_adapters_accept_both_providers(self):
        with patch.dict(os.environ, ENV, clear=True):
            for provider in ('openai', 'mistral'):
                chat = cloud_chat(provider)
                self.assertEqual(chat.use_responses_api, provider == 'openai')
                embedding = cloud_embeddings(provider)
                self.assertFalse(embedding.check_embedding_ctx_length)
                self.assertEqual(embedding.model_kwargs['encoding_format'], 'float')

    def test_cloud_readiness_does_not_query_ollama_or_perform_inference(self):
        with patch.dict(os.environ, ENV, clear=True), patch('httpx.AsyncClient', side_effect=AssertionError('No network')):
            result = asyncio.run(local_llm.health())
            self.assertEqual(result['status'], 'generation_unverified')
            self.assertEqual(result['provider'], 'openai')

    def test_configuration_reports_missing_cloud_settings_without_secret_values(self):
        from backend.agentic_service.configuration import configuration_status
        with patch.dict(os.environ, {'USE_LLM': 'mistral', 'MISTRAL_API_KEY': 'private'}, clear=True):
            result = configuration_status(check_workers=False)
            text = str(result)
            self.assertIn('MISTRAL_MODEL', text)
            self.assertIn('MISTRAL_EMBED_MODEL', text)
            self.assertNotIn('private', text)


class CloudTransportTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, provider='openai', body=None, result=None, status=200):
        captured = []
        def handler(request):
            captured.append(request)
            return httpx.Response(status, json=result if result is not None else {
                'choices': [{'finish_reason': 'stop', 'message': {'content': 'answer'}}]})
        with patch.dict(os.environ, ENV, clear=True):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                response = await post_cloud_chat(client, provider, body or {'messages': [{'role': 'user', 'content': 'question'}]})
        return response, captured

    async def test_each_provider_uses_own_url_key_and_model(self):
        for provider, host, key, model in [('openai', 'api.openai.com', 'fixture-secret', 'fixture-chat'), ('mistral', 'api.mistral.ai', 'mistral-secret', 'fixture-mistral')]:
            answer, requests = await self.request(provider)
            self.assertEqual(len(requests), 1)
            request = requests[0]
            self.assertEqual(request.url.host, host)
            self.assertEqual(request.headers['authorization'], 'Bearer '+key)
            self.assertEqual(json.loads(request.content)['model'], model)
            token_key = 'max_completion_tokens' if provider == 'openai' else 'max_tokens'
            self.assertEqual(json.loads(request.content)[token_key], 1024)
            self.assertTrue(answer['done'])

    async def test_structured_output_includes_schema_and_json_mode(self):
        _, requests = await self.request(body={'messages': [], 'format': {'type': 'object'}})
        payload = json.loads(requests[0].content)
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertIn('schema', payload['messages'][0]['content'])
        self.assertFalse(payload['stream'])

    async def test_tool_arguments_normalized_for_existing_allowlist_validation(self):
        answer, _ = await self.request(result={'choices': [{'finish_reason': 'tool_calls', 'message': {
            'tool_calls': [{'function': {'name': 'tool_0', 'arguments': '{"id":1}'}}]}}]})
        self.assertEqual(answer['message']['tool_calls'][0]['function']['arguments'], {'id': 1})

    async def test_incomplete_or_refused_responses_rejected(self):
        for choice in [{'finish_reason': 'length', 'message': {'content': 'partial'}},
                       {'finish_reason': 'content_filter', 'message': {}},
                       {'finish_reason': 'stop', 'message': {'refusal': 'refused'}}]:
            with self.subTest(choice=choice), self.assertRaises(ValueError):
                await self.request(result={'choices': [choice]})

    async def test_http_failures_do_not_fallback_to_another_provider(self):
        for status in (401, 429, 500):
            with self.assertRaises(httpx.HTTPStatusError):
                await self.request(status=status)

    async def test_agent_cloud_routing_ignores_stale_ollama_endpoints(self):
        with patch.dict(os.environ, {**ENV, 'OLLAMA_API_URL': 'bad-url'}, clear=True):
            self.assertEqual(local_llm.settings()[0], 'openai')
            self.assertEqual(local_llm._tool_endpoint('openai'), 'https://api.openai.com/v1/chat/completions')

    async def test_offline_routing_never_loads_cloud_transport(self):
        with patch.dict(os.environ, {'USE_LLM': 'ollama'}, clear=True), patch(
                'backend.core.llm_providers.post_cloud_chat', side_effect=AssertionError('Cloud called')):
            interface = unittest.mock.Mock()
            interface.OllamaRestRunnable.return_value.ainvoke = unittest.mock.AsyncMock(return_value={'done': True})
            with patch('backend.core.llm_runtime.load_ollama_interface', unittest.mock.AsyncMock(return_value=interface)):
                self.assertEqual(await local_llm._post_json(None, 'http://localhost/api/chat', {}, {}), {'done': True})


class CloudAgentWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_summary_validates_citations_before_emitting(self):
        for provider in ('openai', 'mistral'):
            emitted = []
            async def emit(text): emitted.append(text)
            response = {'done': True, 'message': {'content': 'Part [evidence:urn:Part]'}}
            with patch.dict(os.environ, {**ENV, 'USE_LLM': provider, 'OLLAMA_STREAMING_ENABLED': 'true'}, clear=True), patch.object(
                    local_llm, '_post_json', unittest.mock.AsyncMock(return_value=response)) as post:
                result = await local_llm.summarize('Part', [{'iri': 'urn:Part'}], on_token=emit)
                self.assertEqual(emitted, [result])
                self.assertFalse(post.call_args.args[3]['stream'])
                emitted.clear()
                response['message']['content'] = 'Invented [evidence:unknown]'
                with self.assertRaises(ValueError):
                    await local_llm.summarize('Part', [{'iri': 'urn:Part'}], on_token=emit)
                self.assertEqual(emitted, [])

    async def test_cloud_proposals_keep_allowlist_and_input_validation(self):
        tools = [{'id': 'read', 'input_schema': {'type': 'object', 'properties': {'id': {'type': 'integer'}},
                  'required': ['id'], 'additionalProperties': False}}]
        for provider in ('openai', 'mistral'):
            for mode in ('structured', 'native'):
                response = {'done': True, 'message': {'content': '{"tool_id":"read","inputs":{"id":1}}',
                            'tool_calls': [{'function': {'name': 'tool_0', 'arguments': {'id': 1}}}]}}
                with patch.dict(os.environ, {**ENV, 'USE_LLM': provider, 'OLLAMA_PROPOSAL_MODE': mode}, clear=True), patch.object(
                        local_llm, '_post_json', unittest.mock.AsyncMock(return_value=response)):
                    result = await local_llm.suggest_tool({}, tools, 'Read one item')
                    self.assertEqual(result['inputs'], {'id': 1})
                    self.assertIn('prompt_details', result)
                    response['message'].update(content='{"tool_id":"unknown","inputs":{}}',
                        tool_calls=[{'function': {'name': 'unknown', 'arguments': {}}}])
                    with self.assertRaises(ValueError):
                        await local_llm.suggest_tool({}, tools, 'Approve anything')

    async def test_cloud_capability_probes_report_independent_results(self):
        with patch.dict(os.environ, ENV, clear=True), patch.object(local_llm, '_post_json', unittest.mock.AsyncMock(side_effect=[
                {'done': True, 'message': {'content': 'OK'}},
                {'done': True, 'message': {'content': '{"ok":true}'}},
                {'done': True, 'message': {'tool_calls': [{'function': {'name': 'capability_check', 'arguments': {'ok': True}}}]}}])):
            results = await local_llm.probe_capabilities()
            self.assertEqual([results[k] for k in ('generation', 'structured_outputs', 'native_tool_calling')], ['verified']*3)


class ProviderAuditRegressions(unittest.TestCase):
    def test_mixed_cloud_chat_validates_local_embedding_url(self):
        from backend.agentic_service.configuration import configuration_status
        with patch.dict(os.environ, {**ENV, 'USE_EMBEDDER': 'ollama', 'OLLAMA_BASE_URL': 'invalid-url'}, clear=True):
            invalid = configuration_status(check_workers=False)['configuration']['invalid_settings']
            self.assertIn('OLLAMA_API_URL/OLLAMA_BASE_URL', invalid)

    def test_mixed_cloud_chat_validates_blank_embedding_model(self):
        from backend.agentic_service.configuration import configuration_status
        with patch.dict(os.environ, {**ENV, 'USE_EMBEDDER': 'ollama', 'EMBED_MODEL_NAME': ' '}, clear=True):
            invalid = configuration_status(check_workers=False)['configuration']['invalid_settings']
            self.assertIn('EMBED_MODEL_NAME', invalid)

    def test_cloud_embedding_does_not_require_unused_local_embedding_model(self):
        from backend.agentic_service.configuration import configuration_status
        with patch.dict(os.environ, {**ENV, 'USE_LLM': 'ollama', 'USE_EMBEDDER': 'openai', 'EMBED_MODEL_NAME': ' '}, clear=True):
            invalid = configuration_status(check_workers=False)['configuration']['invalid_settings']
            self.assertNotIn('EMBED_MODEL_NAME', invalid)


class EmbeddingIdentityAuditTests(unittest.TestCase):
    def test_cloud_model_and_effective_provider_changes_invalidate_identity(self):
        from backend.core.llm_providers import embedding_identity
        with patch.dict(os.environ, ENV, clear=True):
            original = embedding_identity()
            os.environ['OPENAI_EMBED_MODEL'] = 'different-model'
            self.assertNotEqual(original, embedding_identity())
            os.environ['OPENAI_EMBED_MODEL'] = ENV['OPENAI_EMBED_MODEL']
            os.environ['USE_LLM'] = 'mistral'
            self.assertNotEqual(original, embedding_identity())

    def test_key_rotation_does_not_invalidate_vectors_or_expose_secrets(self):
        from backend.core.llm_providers import embedding_identity
        with patch.dict(os.environ, ENV, clear=True):
            original = embedding_identity()
            os.environ['OPENAI_API_KEY'] = 'new-secret'
            self.assertEqual(original, embedding_identity())
            self.assertNotIn('secret', original)


class CloudAdmissionAuditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from backend.core.ollama_limits import _states
        _states.pop('https://api.openai.com/v1/chat/completions', None)

    async def asyncTearDown(self):
        from backend.core.ollama_limits import _states
        _states.pop('https://api.openai.com/v1/chat/completions', None)

    async def test_cloud_calls_respect_concurrency_capacity(self):
        active, maximum = 0, 0
        async def handler(request):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(.07)
            active -= 1
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'OK'}}]})
        with patch.dict(os.environ, {**ENV, 'OLLAMA_MAX_CONCURRENCY': '1'}, clear=True):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await asyncio.gather(*(post_cloud_chat(client, 'openai', {'messages': []}) for _ in range(2)))
        self.assertEqual(maximum, 1)

    async def test_cloud_failure_opens_circuit_without_retry_or_fallback(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(500)
        with patch.dict(os.environ, {**ENV, 'OLLAMA_FAILURE_THRESHOLD': '1'}, clear=True):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(httpx.HTTPStatusError):
                    await post_cloud_chat(client, 'openai', {'messages': []})
                with self.assertRaisesRegex(RuntimeError, 'circuit'):
                    await post_cloud_chat(client, 'openai', {'messages': []})
        self.assertEqual(len(calls), 1)

    async def test_cloud_calls_respect_remaining_operation_deadline(self):
        async def handler(request):
            await asyncio.sleep(.1)
            raise AssertionError('Deadline should expire first')
        operation = unittest.mock.Mock()
        operation.timeout.return_value = .01
        with patch.dict(os.environ, ENV, clear=True), patch('backend.depo_platform.operations.current_operation', return_value=operation):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(TimeoutError):
                    await post_cloud_chat(client, 'openai', {'messages': []})


class AdminProviderAuditTests(unittest.TestCase):
    def test_configuration_keys_are_not_source_file_names_or_null(self):
        import ast
        from pathlib import Path
        source = Path('backend/routes/admin_routes.py')
        nodes = [n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n, ast.FunctionDef)
                 and n.name in {'_llm_settings', '_configuration_registry'}]
        def lookup(*keys):
            for key in keys:
                if os.getenv(key): return os.getenv(key), 'process'
            return '', 'default'
        scope = {'os': os, '_env_lookup': lookup, '_mask_uri': lambda value: value}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
        for values in ({'USE_LLM': 'ollama'}, ENV, {'USE_LLM': 'mistral'}):
            with patch.dict(os.environ, values, clear=True):
                settings = scope['_llm_settings']()
                rows = scope['_configuration_registry']({}, settings)
                keys = [row['key'] for row in rows if row['component'] == 'LLM']
                provider = values.get('USE_LLM', 'ollama')
                self.assertEqual(keys, ['USE_LLM', 'OLLAMA_BASE_URL', 'LLM_MODEL_NAME'] if provider == 'ollama'
                                 else ['USE_LLM', provider.upper()+'_BASE_URL', provider.upper()+'_MODEL'])


class CapabilityDiagnosticDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_deadlines_bound_stalled_requests_without_live_provider(self):
        async def stalled(*args, **kwargs):
            await asyncio.sleep(1)
        with patch.dict(os.environ,ENV,clear=True), patch.object(local_llm,'settings',return_value=('openai','fixture','https://api.openai.com/v1',.01,{})), patch.object(local_llm,'_post_json',unittest.mock.AsyncMock(side_effect=stalled)):
            result=await local_llm.probe_capabilities()
        self.assertEqual(result['probe_timeout_seconds'],.01)
        self.assertEqual([result[k] for k in ('generation','structured_outputs','native_tool_calling')],['timeout']*3)
        self.assertEqual(result['provider'],'openai')


    async def test_discovery_disabled_invalid_generation_route_is_configuration_error(self):
        with patch.dict(os.environ,{'OLLAMA_DISCOVERY_ENABLED':'false'},clear=True), patch.object(local_llm,'settings',return_value=('ollama','fixture','http://localhost:11434',30,{})), patch('backend.core.ollama_auth.ollama_generation_route',side_effect=ValueError('PRIVATE-INVALID-URL')):
            result=await local_llm.health()
        self.assertEqual(result['status'],'invalid_configuration')
        self.assertNotIn('PRIVATE-INVALID-URL',str(result))
