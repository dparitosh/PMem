"""Readiness must expose invalid REST settings without leaking their values."""
import os
import unittest
from unittest.mock import patch

from backend.agentic_service.configuration import configuration_status


class LlmReadinessConfigurationTests(unittest.TestCase):
    def test_preflight_defers_worker_presence_but_runtime_requires_it(self):
        with patch.dict(os.environ, {'AGENTIC_EXECUTION_MODE': 'worker', 'AUTH_MODE': 'token'}, clear=True):
            preflight = configuration_status(check_workers=False)['configuration']['invalid_settings']
            runtime = configuration_status()['configuration']['invalid_settings']
        self.assertNotIn('AGENTIC_WORKFLOW_WORKER', preflight)
        self.assertIn('AGENTIC_WORKFLOW_WORKER', runtime)

    def settings_errors(self, **settings):
        with patch.dict(os.environ, settings, clear=True):
            return configuration_status()['configuration']['invalid_settings']

    def test_conflicting_roots_are_reported_without_values(self):
        errors = self.settings_errors(OLLAMA_API_URL='http://host-a/ollama',
                                      OLLAMA_BASE_URL='http://host-b/ollama')
        self.assertIn('OLLAMA_API_URL/OLLAMA_BASE_URL', errors)
        self.assertNotIn('host-a', str(errors))

    def test_bad_auth_and_chat_operation_are_reported(self):
        errors = self.settings_errors(OLLAMA_API_KEY='secret',
                                      OLLAMA_API_KEY_HEADER='invalid',
                                      OLLAMA_CHAT_API_URL='http://host/api/generate')
        self.assertIn('OLLAMA_API_KEY_HEADER/OLLAMA_REQUIRE_HTTPS', errors)
        self.assertIn('OLLAMA_CHAT_API_URL', errors)
        self.assertNotIn('secret', str(errors))

    def test_http_generate_only_remains_valid(self):
        errors = self.settings_errors(OLLAMA_API_URL='http://host/ollama/api/generate',
                                      OLLAMA_DISCOVERY_ENABLED='false',
                                      ONTOLOGY_AGENT_LLM_ENABLED='true')
        self.assertFalse(any(key.startswith('OLLAMA_') for key in errors))

    def test_bad_chat_route_has_secret_free_recovery_action(self):
        with patch.dict(os.environ, {'USE_LLM':'ollama',
                'OLLAMA_CHAT_API_URL':'http://private-fixture/api/generate'}, clear=True):
            result=configuration_status()['configuration']
        self.assertIn('/api/chat',result['actions']['OLLAMA_CHAT_API_URL'])
        self.assertNotIn('private-fixture',str(result))

    def test_aoi_does_not_validate_unused_ollama_chat_route(self):
        errors=self.settings_errors(USE_LLM='aoi',USE_EMBEDDER='aoi',
            AOI_MODEL='aoi-chat',AOI_EMBED_MODEL='aoi-embedding',
            AOI_BASE_URL='http://127.0.0.1:8020/v1',AOI_GATEWAY_TOKEN='fixture-token-of-at-least-32-characters',
            EMBEDDING_VECTOR_DIMENSIONS='1536',OLLAMA_CHAT_API_URL='http://unused/api/generate')
        self.assertNotIn('OLLAMA_CHAT_API_URL',errors)

    def test_valid_explicit_chat_preserves_generate_route(self):
        errors=self.settings_errors(OLLAMA_API_URL='http://host/ollama/api/generate',
            OLLAMA_CHAT_API_URL='http://host/ollama/api/chat')
        self.assertNotIn('OLLAMA_CHAT_API_URL',errors)

    def test_blank_models_and_invalid_companion_flag_are_reported(self):
        errors = self.settings_errors(LLM_MODEL_NAME=' ', EMBED_MODEL_NAME='',
                                      COMPANION_LLM_ENABLED='yes')
        for key in ('LLM_MODEL_NAME', 'EMBED_MODEL_NAME', 'COMPANION_LLM_ENABLED'):
            self.assertIn(key, errors)
