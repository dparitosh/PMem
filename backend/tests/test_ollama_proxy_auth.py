import unittest
from unittest.mock import patch
from backend.core.ollama_auth import ollama_headers, ollama_base_url
class OllamaProxyAuthTests(unittest.TestCase):
    def test_api_url_and_legacy_compatibility(self):
        with patch.dict('os.environ', {'OLLAMA_API_URL': 'http://example.azure-api.net/ollama/api/chat'}, clear=True):
            self.assertEqual(ollama_base_url(), 'http://example.azure-api.net/ollama')
        with patch.dict('os.environ', {'OLLAMA_BASE_URL': 'http://localhost:11434'}, clear=True):
            self.assertEqual(ollama_base_url(), 'http://localhost:11434')
        with patch.dict('os.environ', {'OLLAMA_API_URL': 'http://example/ollama/api/chat', 'OLLAMA_BASE_URL': 'http://example/ollama'}, clear=True):
            self.assertEqual(ollama_base_url(), 'http://example/ollama')
    def test_conflicting_and_unsafe_api_urls_are_rejected(self):
        with patch.dict('os.environ', {'OLLAMA_API_URL': 'http://one', 'OLLAMA_BASE_URL': 'http://two'}, clear=True):
            with self.assertRaises(ValueError): ollama_base_url()
        for url in ('file:///tmp/ollama', 'http://user:secret@example', 'http://example?key=secret'):
            with self.assertRaises(ValueError): ollama_base_url(url)
    def test_apim_subscription_and_local_compatibility(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(ollama_headers('http://example.azure-api.net/ollama', 'fixture'), {'Ocp-Apim-Subscription-Key': 'fixture'})
            self.assertEqual(ollama_headers('http://localhost:11434', 'fixture'), {'api-key': 'fixture'})
            self.assertEqual(ollama_headers('http://localhost:11434', ''), {})
    def test_explicit_header_and_invalid_header(self):
        self.assertEqual(ollama_headers('https://proxy.example/ollama', 'fixture', header_name='Authorization'), {'Authorization': 'Bearer fixture'})
        with self.assertRaises(ValueError): ollama_headers('https://proxy.example', 'fixture', header_name='invalid')
