"""Exercise the actual I/O helper without importing database-backed routers."""
import ast
import asyncio
from pathlib import Path
import unittest


class AgentIOTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        path = Path(__file__).resolve().parents[1] / 'agentic_service' / 'router.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        helper = next(node for node in tree.body
                      if isinstance(node, ast.AsyncFunctionDef) and node.name == '_agent_io')
        scope = {'asyncio': asyncio}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(path), 'exec'), scope)
        self.helper = scope['_agent_io']

    async def test_telemetry_operation_keywords_reach_callback(self):
        def start(*, operation, request_id):
            return {'operation': operation, 'request_id': request_id}, 123
        for operation in ('knowledge_companion', 'tool', 'workflow'):
            with self.subTest(operation=operation):
                record, started = await self.helper(start, operation=operation, request_id='request-1')
                self.assertEqual(record, {'operation': operation, 'request_id': 'request-1'})
                self.assertEqual(started, 123)

    async def test_callback_keyword_and_positional_arguments_are_preserved(self):
        def write(key, *, callback):
            return key, callback
        self.assertEqual(await self.helper(write, 'run-1', callback='value'), ('run-1', 'value'))

    async def test_callback_failure_propagates(self):
        def fail():
            raise RuntimeError('storage unavailable')
        with self.assertRaisesRegex(RuntimeError, 'storage unavailable'):
            await self.helper(fail)


if __name__ == '__main__':
    unittest.main()
