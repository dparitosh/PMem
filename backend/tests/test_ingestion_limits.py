"""Limit parsing uses the same byte-count contract as Windows preflight."""
import os
import unittest
from unittest.mock import patch
from backend.ingestion_service.tabular import _positive_setting


class IngestionLimitTests(unittest.TestCase):
    def test_missing_setting_uses_documented_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_positive_setting('DEPO_MAX_INGEST_BYTES', 524288000), 524288000)

    def test_console_commands_units_and_nonpositive_values_are_rejected(self):
        for raw in ('524288000cls', '500MB', '', '0', '-1', '1.5', '524_288_000',
                    '9223372036854775808', '9' * 5000):
            with self.subTest(raw_length=len(raw)), patch.dict(os.environ, {'DEPO_MAX_INGEST_BYTES': raw}):
                with self.assertRaises(RuntimeError) as failure:
                    _positive_setting('DEPO_MAX_INGEST_BYTES', 524288000)
                self.assertNotIn('524288000cls', str(failure.exception))

    def test_supported_values_match_preflight(self):
        for raw in ('524288000', '1', ' +67108864 ', '9223372036854775807', '0001'):
            with self.subTest(raw=raw), patch.dict(os.environ, {'DEPO_MAX_INGEST_BYTES': raw}):
                self.assertEqual(_positive_setting('DEPO_MAX_INGEST_BYTES', 524288000), int(raw))

    def test_leading_zeros_do_not_trigger_python_integer_string_limit(self):
        with patch.dict(os.environ, {'DEPO_MAX_INGEST_BYTES': '0' * 5000 + '1'}):
            self.assertEqual(_positive_setting('DEPO_MAX_INGEST_BYTES', 524288000), 1)


if __name__ == '__main__':
    unittest.main()
