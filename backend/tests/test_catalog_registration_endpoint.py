import ast
import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

class CatalogEndpointTests(unittest.TestCase):
    def test_origin_and_api_root_use_same_registration_route(self):
        source = Path('backend/data_product_service/router.py').read_text(encoding='utf-8')
        function = next(node for node in ast.parse(source).body if isinstance(node, ast.AsyncFunctionDef) and node.name == '_register_catalog')
        module = ast.Module(body=[function], type_ignores=[])
        seen = []
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def put(self, url, **kwargs):
                seen.append(url)
                return SimpleNamespace(raise_for_status=lambda: None)
        fake_network = SimpleNamespace(gateway_subscription_headers=lambda endpoint: {})
        namespace = dict(os=os, datetime=datetime, timezone=timezone, timedelta=timedelta,
                         _now=lambda: datetime.now(timezone.utc).isoformat(),
                         _catalog_payload=lambda record: {},
                         httpx=SimpleNamespace(AsyncClient=Client, HTTPError=RuntimeError))
        exec(compile(module, '<catalog registration>', 'exec'), namespace)
        with patch.dict('sys.modules', {'backend.depo_platform.network': fake_network}):
            for root in ('http://catalog:8016', 'http://catalog:8016/api/v1/'):
                with self.subTest(root=root), patch.dict(os.environ, {'DATA_CATALOG_URL': root, 'CATALOG_SERVICE_TOKEN': 'test-token'}):
                    result = asyncio.run(namespace['_register_catalog']({'product_id': 'sample', 'version': '1.0.0'}))
                    self.assertEqual(result['status'], 'published')
                    self.assertEqual(seen[-1], 'http://catalog:8016/api/v1/catalog/products/sample/versions/1.0.0')

if __name__ == '__main__': unittest.main()
