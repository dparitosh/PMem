import unittest
from unittest.mock import patch
from backend.core.ollama_auth import ollama_headers
class OllamaProxyAuthTests(unittest.TestCase):
    def test_apim_subscription_and_local_compatibility(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(ollama_headers('http://example.azure-api.net/ollama', 'fixture'), {'Ocp-Apim-Subscription-Key': 'fixture'})
            self.assertEqual(ollama_headers('http://localhost:11434', 'fixture'), {'api-key': 'fixture'})
            self.assertEqual(ollama_headers('http://localhost:11434', ''), {})
    def test_explicit_header_and_invalid_header(self):
        self.assertEqual(ollama_headers('https://proxy.example/ollama', 'fixture', header_name='Authorization'), {'Authorization': 'Bearer fixture'})
        with self.assertRaises(ValueError): ollama_headers('https://proxy.example', 'fixture', header_name='invalid')
