import ast
import os
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from backend.agentic_service.chat_request import ChatRequest


class CompanionBoundaryTests(unittest.TestCase):
    def test_rejects_non_text_and_oversize_messages(self):
        for value in ([], {'message': 'text'}, 42, '', 'a' * 4001):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValidationError):
                ChatRequest(message=value)

    def test_context_retains_only_bounded_scope(self):
        request = ChatRequest(message='product', graph_context={'ontology': 'qif', 'visibleGraph': {'nodes': [{'label': 'untrusted'}]}})
        self.assertEqual(request.graph_context.model_dump(), {'ontology': 'qif', 'ontology_prefix': ''})
        with self.assertRaises(ValidationError):
            ChatRequest(message='product', graph_context={'ontology': 'x' * 129})
        with self.assertRaises(ValidationError):
            ChatRequest(message='product', graph_context={'ontology_prefix': 'x' * 129})

    def test_rotated_caller_read_key_overrides_stale_environment(self):
        path = Path(__file__).resolve().parents[1] / 'agentic_service/transport_auth.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'downstream_headers')
        scope = {'os': os, 'Request': object}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), scope)
        network = ModuleType('backend.depo_platform.network')
        network.gateway_subscription_headers = lambda endpoint: {'Ocp-Apim-Subscription-Key': 'gateway-key'}
        with patch.dict(sys.modules, {'backend.depo_platform.network': network}), patch.dict(os.environ, {'AUTH_MODE': 'token', 'GRAPH_READ_TOKEN': 'stale-key'}):
            headers = scope['downstream_headers'](SimpleNamespace(headers={'authorization': 'Bearer rotated-key'}), 'http://graph/api/v1', graph_read=True)
        self.assertEqual(headers['Authorization'], 'Bearer rotated-key')
        self.assertEqual(headers['Ocp-Apim-Subscription-Key'], 'gateway-key')

    def test_graph_filter_is_parameterized(self):
        from backend.graph_service.query_repository import ONTOLOGY_SEARCH_NODES
        self.assertIn('n.ontology_id = $ontology_id', ONTOLOGY_SEARCH_NODES)


if __name__ == '__main__':
    unittest.main()
