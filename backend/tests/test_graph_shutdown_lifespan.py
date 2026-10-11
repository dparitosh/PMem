"""Exercise graph shutdown without requiring a live Neo4j or FastAPI runtime."""
import ast
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import unittest
from unittest.mock import MagicMock


class GraphShutdownTests(unittest.IsolatedAsyncioTestCase):
    def lifecycle(self):
        source = Path(__file__).resolve().parents[1] / 'graph_service' / 'app.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        hook = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'graph_lifespan')
        publisher = MagicMock()
        scope = {'asynccontextmanager': asynccontextmanager, 'to_thread': asyncio.to_thread, 'publisher': publisher}
        exec(compile(ast.Module(body=[hook], type_ignores=[]), str(source), 'exec'), scope)
        return scope['graph_lifespan'], publisher, tree

    async def test_close_on_normal_shutdown(self):
        hook, publisher, _ = self.lifecycle()
        async with hook():
            publisher.close.assert_not_called()
        publisher.close.assert_called_once_with()

    async def test_close_on_exceptional_shutdown(self):
        hook, publisher, _ = self.lifecycle()
        with self.assertRaisesRegex(RuntimeError, 'shutdown failure'):
            async with hook():
                raise RuntimeError('shutdown failure')
        publisher.close.assert_called_once_with()

    async def test_factory_receives_lifespan_hook(self):
        _, _, tree = self.lifecycle()
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        factory = next(n for n in calls if isinstance(n.func, ast.Name) and n.func.id == 'create_service_app')
        self.assertTrue(any(k.arg == 'lifespan_hook' and isinstance(k.value, ast.Name) and k.value.id == 'graph_lifespan' for k in factory.keywords))
        self.assertFalse(any(isinstance(n.func, ast.Attribute) and n.func.attr == 'add_event_handler' for n in calls))


if __name__ == '__main__':
    unittest.main()
