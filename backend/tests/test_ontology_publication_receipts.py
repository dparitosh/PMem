import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest

class ApiError(Exception):
    def __init__(self, status, detail): self.status_code, self.detail = status, detail

class PublicationReceiptsTests(unittest.IsolatedAsyncioTestCase):
    def operation(self, approved=True, valid=True, lookup_body=None, response_body=None, existing=None):
        content = b'<urn:Part> <urn:label> "Part" .'
        records, calls = dict(existing or {}), []
        class Response:
            status_code = 404
            def raise_for_status(self): pass
            def json(self): return response_body if response_body is not None else {'status': 'success', 'ontology_id': 'demo' if valid else 'wrong', 'publication_id': hashlib.sha256(content).hexdigest(), 'resources': 1, 'relationships': 0}
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, *args, **kwargs): return SimpleNamespace(status_code=404, json=lambda: lookup_body if lookup_body is not None else {'detail': 'Publication receipt was not found'})
            async def post(self, *args, **kwargs): calls.append(kwargs); return Response()
        async def thread(fn, *args): return fn(*args)
        scope = {'Any': object, 'Request': object, 'HTTPException': ApiError, 'hashlib': hashlib,
                 'approval_identity': lambda *args, **kwargs: 'approver', 'run_in_threadpool': thread,
                 'service_url': lambda *args: 'http://graph', 'service_bearer_headers': lambda *args, **kwargs: {},
                 'httpx': SimpleNamespace(AsyncClient=Client, HTTPError=OSError),
                 'catalog': SimpleNamespace(get=lambda key: {'lifecycle_status': 'approved' if approved else 'draft', 'prefix': 'demo', 'validation': {'rdf_format': 'turtle'}}, read_artifact=lambda key: ({'lifecycle_status': 'approved' if approved else 'draft'}, content)),
                 'graph_publications': SimpleNamespace(get=records.get, put=lambda key, value: records.update({key: value}))}
        tree = ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8'))
        nodes = [node for node in tree.body if getattr(node, 'name', '') in {'ontology_publication_status', '_publish_registered_ontology'}]
        for node in nodes: node.decorator_list = []
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<publication>', 'exec'), scope)
        return scope['_publish_registered_ontology'], records, calls

    async def test_draft_cannot_publish(self):
        operation, records, calls = self.operation(approved=False)
        with self.assertRaises(ApiError) as failure: await operation('demo', {}, object())
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(calls, [])

    async def test_exact_receipt_required_before_reporting_success(self):
        operation, records, calls = self.operation()
        result = await operation('demo', {}, object())
        self.assertEqual(result['status'], 'published')
        self.assertEqual(len(calls), 1)
        operation, records, calls = self.operation(valid=False)
        with self.assertRaises(ApiError) as failure: await operation('demo', {}, object())
        self.assertEqual(failure.exception.status_code, 503)
        self.assertEqual(records['demo']['status'], 'publishing')

    async def test_gateway_route_missing_does_not_authorize_a_write(self):
        operation, records, calls = self.operation(lookup_body={'detail': 'Not Found'})
        with self.assertRaises(ApiError) as failure: await operation('demo', {}, object())
        self.assertEqual(failure.exception.status_code, 503)
        self.assertEqual(calls, [])

    async def test_nonobject_publication_receipt_is_unverified(self):
        operation, records, calls = self.operation(response_body=[])
        with self.assertRaises(ApiError) as failure: await operation('demo', {}, object())
        self.assertEqual(failure.exception.status_code, 503)

    async def test_retry_retains_the_original_approver(self):
        digest = hashlib.sha256(b'<urn:Part> <urn:label> "Part" .').hexdigest()
        operation, records, calls = self.operation(existing={'demo': {'ontology_id': 'demo', 'publication_id': digest, 'approved_by': 'original-reviewer'}})
        result = await operation('demo', {}, object())
        self.assertEqual(result['approved_by'], 'original-reviewer')
