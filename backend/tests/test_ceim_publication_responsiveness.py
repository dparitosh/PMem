"""CPU-heavy publication preparation must leave the service loop responsive."""
import asyncio
import importlib
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class PublicationResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_preparation_runs_off_event_loop_before_graph_write(self):
        router = importlib.import_module('backend.ceim_service.router')
        loop_thread = threading.get_ident()
        threads = []

        def normalize(_payload):
            threads.append(threading.get_ident())
            return {'entities': [], 'relationships': []}

        def validate(**_kwargs):
            threads.append(threading.get_ident())
            time.sleep(.03)
            return {'conforms': True, 'triple_count': 0, 'ceim_version': '0.1.0'}

        def serialize(**_kwargs):
            threads.append(threading.get_ident())
            return ''

        contract = SimpleNamespace(validate_projection=validate, turtle_projection=serialize)
        with patch.object(router, 'approval_identity', return_value='test'), \
             patch.object(router, 'resolve_approved_release', new=AsyncMock(return_value={'asset_id':'test','version':'1'})), \
             patch.object(router, 'normalize_batch', side_effect=normalize), \
             patch.object(router, 'contract', contract), \
             patch.object(router, '_publish_to_graph', new=AsyncMock(return_value={'publication_id':'test'})) as publish, \
             patch.dict('os.environ', {'DEPO_CEIM_IDENTITY_MODE':'legacy'}):
            task = asyncio.create_task(router.publish_graph({'standard':'ap242','publication_id':'test'}, SimpleNamespace()))
            ticks = 0
            while not task.done():
                await asyncio.sleep(.005)
                ticks += 1
            result = await task
        self.assertEqual(result['status'], 'published')
        self.assertTrue(threads)
        self.assertTrue(all(thread != loop_thread for thread in threads))
        self.assertGreater(ticks, 1)
        publish.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
