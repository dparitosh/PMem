import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager


def actual(names, scope):
    tree = ast.parse(Path('backend/data_product_service/router.py').read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for node in nodes: node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<service functions>', 'exec'), scope)
    return scope


class ServiceFailureTests(unittest.TestCase):
    def test_nested_secrets_are_rejected_before_persistence(self):
        scope = actual({'_reject_secrets'}, {})
        for name in ('headers', 'credentials', 'client_secret', 'api_key', 'password'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                scope['_reject_secrets']({'sources': [{name: 'private'}]})
        scope['_reject_secrets']({'approval_token': 'caller', 'sources': [{'id': 'public'}]})

    def test_invalid_limits_return_validation_error(self):
        class HTTPException(Exception):
            def __init__(self, code, message): self.status_code = code
        fn = actual({'reconcile'}, dict(Request=object, HTTPException=HTTPException,
            approval_identity=lambda *a, **k: None, reconcile_pending=AsyncMock()))['reconcile']
        for limit in (None, 'abc', True, 0, 1001, 1.5):
            with self.subTest(limit=limit), self.assertRaises(HTTPException) as failure:
                asyncio.run(fn({'limit': limit}, object()))
            self.assertEqual(failure.exception.status_code, 422)

    def test_delivered_revocation_is_not_pending(self):
        record = {'status': 'pending_catalog_registration', 'lifecycle_state': 'revoked'}
        @asynccontextmanager
        async def lock(key): yield True
        store = SimpleNamespace(due_pending=lambda n: [('p:1', record)], get=lambda key: record,
                                compare_and_put=lambda *a: True)
        scope = actual({'reconcile_pending'}, dict(asyncio=asyncio, _product_io=asyncio.to_thread, store=store, _product_lock=lock,
            _register_catalog=AsyncMock(return_value={**record, 'status': 'revoked'})))
        result = asyncio.run(scope['reconcile_pending']())
        self.assertEqual(result, {'examined': 1, 'published': 0, 'revoked': 1, 'pending': 0})

    def test_cancelled_thread_work_finishes_before_operation_can_release_lock(self):
        import threading
        async def check():
            entered, finish = threading.Event(), threading.Event()
            def blocking():
                entered.set()
                finish.wait(2)
            fn = actual({'_product_io'}, {'asyncio': asyncio})['_product_io']
            task = asyncio.create_task(fn(blocking))
            await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(.01)
            self.assertFalse(task.done())
            finish.set()
            with self.assertRaises(asyncio.CancelledError): await task
        asyncio.run(check())

    def test_schema_selection_cannot_fall_back_to_public_tables(self):
        from backend.depo_platform.postgres_schema import select_schema, initialise_schema
        from unittest.mock import Mock, patch
        import os
        for fn in (select_schema, initialise_schema):
            cursor = Mock()
            cursor.fetchone.return_value = (True,)
            with patch.dict(os.environ, {'DEPO_DATABASE_SCHEMA': 'semantic'}, clear=True): fn(cursor)
            self.assertEqual(cursor.execute.call_args.args[0], 'SET search_path TO "semantic"')
