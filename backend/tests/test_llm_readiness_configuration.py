"""Readiness must expose invalid REST settings without leaking their values."""
import os
import unittest
from unittest.mock import patch

from backend.agentic_service.configuration import configuration_status


class LlmReadinessConfigurationTests(unittest.TestCase):
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

    def test_blank_models_and_invalid_companion_flag_are_reported(self):
        errors = self.settings_errors(LLM_MODEL_NAME=' ', EMBED_MODEL_NAME='',
                                      COMPANION_LLM_ENABLED='yes')
        for key in ('LLM_MODEL_NAME', 'EMBED_MODEL_NAME', 'COMPANION_LLM_ENABLED'):
            self.assertIn(key, errors)
