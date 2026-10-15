import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from backend.depo_platform.operations import OperationContext, operation_scope, current_operation
from backend.agentic_service.tool_timeouts import tool_timeout_seconds
from backend.depo_platform.network import timeout_configuration_warnings


class OperationTests(unittest.TestCase):
    def test_deadline_caps_tools_and_scope_resets_after_failure(self):
        context = OperationContext('run', (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat())
        with self.assertRaises(ValueError):
            with operation_scope(context):
                self.assertGreater(tool_timeout_seconds({'id':'engineering.publish'}, {}), 0)
                self.assertLessEqual(tool_timeout_seconds({'id':'engineering.publish'}, {}), 5)
                raise ValueError('test')
        self.assertIsNone(current_operation())

    def test_expired_deadline_prevents_dispatch(self):
        context = OperationContext('run', (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
        with operation_scope(context), self.assertRaises(TimeoutError):
            tool_timeout_seconds({'id':'ontology.export'}, {})

    def test_engineering_operation_gets_full_budget(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(tool_timeout_seconds({'id':'engineering.publish'}, {}), 1380)
            self.assertEqual(timeout_configuration_warnings(), [])

    def test_short_explicit_deadline_is_reported(self):
        with patch.dict(os.environ, {'AGENTIC_RUN_TIMEOUT_SECONDS':'30'}, clear=True):
            self.assertTrue(timeout_configuration_warnings())

    def test_shared_ollama_admission_obeys_workflow_deadline(self):
        import asyncio
        from backend.core.ollama_limits import request_slot
        async def run():
            context = OperationContext('run', (datetime.now(timezone.utc)+timedelta(seconds=.05)).isoformat())
            with operation_scope(context):
                async with request_slot('test-operation-deadline'):
                    await asyncio.sleep(1)
        with self.assertRaises(TimeoutError): asyncio.run(run())
