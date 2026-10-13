import subprocess
import unittest
from unittest.mock import patch
from backend.ingestion_service.conversion_process import convert_engineering
from backend.ontology_service.merge_semantics import validate_merge


class ConversionDeadlineTests(unittest.TestCase):
    def test_conversion_timeout_is_reported_without_a_result(self):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 1)):
            with self.assertRaisesRegex(ValueError, 'worker was terminated'):
                convert_engineering(source='test')

    def test_merge_timeout_cannot_return_approval_evidence(self):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 1)):
            with self.assertRaisesRegex(ValueError, 'worker was terminated'):
                validate_merge([], [])
