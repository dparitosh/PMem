"""Offline regression checks for shared service routing."""
import os
import unittest
from unittest.mock import patch
from backend.depo_platform.service_urls import service_url

class ServiceUrls(unittest.TestCase):
    def test_valid_http_and_gateway_base(self):
        for url in ('http://10.0.2.16:8018/api/v1/', 'https://gateway.example/depo/ceim/api/v1'):
            with patch.dict(os.environ, {'CEIM_SERVICE_URL': url}, clear=True):
                self.assertEqual(service_url('CEIM_SERVICE_URL', ''), url.rstrip('/'))

    def test_invalid_endpoint_is_rejected(self):
        for url in ('https://user:secret@host/api', 'https://host/api?key=secret',
                    'https://<gateway>/api', 'https://host:bad/api',
                    'https://host/%2e%2e/api', 'file:///tmp/api'):
            with self.subTest(url=url), patch.dict(os.environ, {'CEIM_SERVICE_URL': url}, clear=True):
                with self.assertRaises(RuntimeError):
                    service_url('CEIM_SERVICE_URL', '')

    def test_no_fallback_for_any_production_alias_or_gateway(self):
        for key in ('DEPO_ENV', 'ENVIRONMENT', 'APP_ENV', 'DEPLOYMENT_ENV', 'DEPO_ROUTING_MODE'):
            with patch.dict(os.environ, {key: 'gateway' if key == 'DEPO_ROUTING_MODE' else 'production'}, clear=True):
                with self.assertRaises(RuntimeError):
                    service_url('CEIM_SERVICE_URL', 'http://127.0.0.1:8018')

    def test_development_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(service_url('CEIM_SERVICE_URL', 'http://127.0.0.1:8018'), 'http://127.0.0.1:8018')

if __name__ == '__main__':
    unittest.main()
