import unittest
from types import SimpleNamespace
from backend.agentic_service.stream_errors import stream_failure


class StreamErrorTests(unittest.TestCase):
    def test_timeout_has_safe_action_and_correlation(self):
        error = SimpleNamespace(status_code=504, headers={'X-DEPO-Run-ID': 'run-1'}, detail='secret upstream detail')
        event = stream_failure(error, 'request-1')
        self.assertEqual(event['category'], 'timed_out')
        self.assertEqual(event['run_id'], 'run-1')
        self.assertEqual(event['request_id'], 'request-1')
        self.assertNotIn('secret', str(event))

    def test_authentication_and_unexpected_errors(self):
        self.assertEqual(stream_failure(SimpleNamespace(status_code=403), 'r')['category'], 'authentication_rejected')
        self.assertEqual(stream_failure(RuntimeError('secret'), 'r')['category'], 'service_unavailable')
        self.assertEqual(stream_failure(TimeoutError(), 'r')['category'], 'timed_out')
