"""Dependency-free gateway credential regression tests."""
import os
import unittest
from unittest.mock import patch
from backend.depo_platform.network import gateway_subscription_headers


class GatewayScopeTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            'DEPO_API_GATEWAY_URL': 'https://Gateway.example/depo',
            'DEPO_APIM_SUBSCRIPTION_KEY': 'fixture-only',
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_equivalent_origin(self):
        self.assertEqual(gateway_subscription_headers('https://gateway.example:443/depo/graph'),
                         {'Ocp-Apim-Subscription-Key': 'fixture-only'})

    def test_foreign_and_traversal_targets(self):
        for target in (
            'http://gateway.example/depo/graph',
            'https://evil.example/depo/graph',
            'https://gateway.example/depox/graph',
            'https://gateway.example/depo/../other',
            'https://gateway.example/depo/%2e%2e/other',
            'https://gateway.example/depo/a%2f..%2f../other',
            'https://user:secret@gateway.example/depo/graph',
            'https://gateway.example:bad/depo/graph',
        ):
            with self.subTest(target=target):
                self.assertEqual(gateway_subscription_headers(target), {})

    def test_no_subscription(self):
        os.environ['DEPO_APIM_SUBSCRIPTION_KEY'] = ''
        self.assertEqual(gateway_subscription_headers('https://gateway.example/depo/graph'), {})
