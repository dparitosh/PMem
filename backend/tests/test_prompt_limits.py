import os
import unittest
from unittest.mock import patch
from backend.agentic_service.prompt_limits import bounded_prompt_json


class PromptLimitTests(unittest.TestCase):
    def test_utf8_size_is_bounded_without_truncating_json(self):
        with patch.dict(os.environ, {'AGENTIC_MAX_PROMPT_BYTES': '16384'}):
            self.assertIn('evidence', bounded_prompt_json({'evidence': 'valid'}))
            with self.assertRaises(ValueError):
                bounded_prompt_json({'evidence': '\u20ac' * 6000})

    def test_invalid_limits_and_nonfinite_values_fail_closed(self):
        for limit in ('0', 'invalid', '1048577'):
            with self.subTest(limit=limit), patch.dict(os.environ, {'AGENTIC_MAX_PROMPT_BYTES': limit}), self.assertRaises(ValueError):
                bounded_prompt_json({})
        with self.assertRaises(ValueError):
            bounded_prompt_json({'value': float('nan')})
