"""Exercise catalog handlers without installing service runtimes."""
import ast
from dataclasses import dataclass
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit
import unittest


class Router:
    def __init__(self, **kwargs): self.handlers = {}
    def get(self, path, **kwargs):
        def register(function):
            self.handlers[path] = function
            return function
        return register


class URL:
    def __init__(self, value): self.value = value; self.path = urlsplit(value).path
    def replace(self, **kwargs):
        parts = urlsplit(self.value)
        return urlunsplit((parts.scheme, parts.netloc, kwargs.get('path', parts.path),
                           kwargs.get('query', parts.query), kwargs.get('fragment', parts.fragment)))


class OdataDiscoveryTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'depo_platform/odata.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        scope = {'dataclass': dataclass, 'sha256': sha256, 'escape': escape, 'Iterable': Iterable,
                 'APIRouter': Router, 'Request': object, 'Response': object,
                 'JSONResponse': lambda data, **kwargs: NS(data=data, **kwargs), '__name__': __name__}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
        self.router = scope['create_odata_catalog_router'](service_name='Test',
            capabilities=[scope['ServiceCapability']('Read', '/api/v1/items')])

    def test_context_preserves_gateway_prefix_and_slash_variants(self):
        for suffix in ['/odata', '/odata/']:
            request = NS(url=URL('https://example.test/graph' + suffix))
            response = self.router.handlers[suffix.removeprefix('/odata')](request)
            self.assertEqual(response.data['@odata.context'], 'https://example.test/graph/odata/$metadata')

    def test_every_manifest_service_has_discovery_and_shared_runtime(self):
        root = Path(__file__).resolve().parents[2]
        manifest = json.loads((root / 'infra/deployment/services.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['services']), 10)
        for service in manifest['services']:
            module = service['module'].split(':')[0]
            source = (root / (module.replace('.', '/') + '.py')).read_text(encoding='utf-8')
            self.assertIn('create_odata_catalog_router(', source, service['id'])
            self.assertIn('create_service_app(', source, service['id'])


if __name__ == '__main__': unittest.main()
