"""Dependency-free regression checks for the plugin's upstream boundary."""
import os
import unittest
from unittest.mock import patch

from mbse_plugin.upstream import configuration, require_durable_run


class UpstreamContractTests(unittest.TestCase):
    def test_execution_key_and_optional_gateway_header(self):
        with patch.dict(os.environ, {'DEPO_INGESTION_URL': 'https://gateway/ingestion/api/v1/',
                                    'DEPO_INGESTION_TOKEN': 'execution-key',
                                    'DEPO_APIM_SUBSCRIPTION_KEY': 'gateway-key'}, clear=True):
            base, headers = configuration()
        self.assertEqual(base, 'https://gateway/ingestion/api/v1')
        self.assertEqual(headers, {'Authorization': 'Bearer execution-key',
                                  'Ocp-Apim-Subscription-Key': 'gateway-key'})

    def test_invalid_urls_are_rejected(self):
        for url in ('', 'ftp://host/api/v1', 'http://host', 'http://user:secret@host/api/v1',
                    'http://host/api/v1?key=secret', 'http://host/api/v1#fragment',
                    'http://host:invalid/api/v1'):
            with self.subTest(url=url), patch.dict(os.environ, {
                    'DEPO_INGESTION_URL': url, 'DEPO_INGESTION_TOKEN': 'key'}, clear=True):
                with self.assertRaises(ValueError):
                    configuration()

    def test_missing_execution_key_is_rejected(self):
        with patch.dict(os.environ, {'DEPO_INGESTION_URL': 'http://host/api/v1'}, clear=True):
            with self.assertRaises(ValueError):
                configuration()

    def test_import_requires_durable_run(self):
        for result in (None, [], {}, {'run_manifest': {}},
                       {'run_manifest': {'run_id': ' '}}, {'run_manifest': {'run_id': 1}}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                require_durable_run(result)
        result = {'run_manifest': {'run_id': 'run-1'}}
        self.assertIs(require_durable_run(result), result)


if __name__ == '__main__':
    unittest.main()
