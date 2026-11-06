import os
import io
import pickle
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.ingestion_service.conversion_process import convert_engineering, BoundedResultWriter, ResultLimitExceeded


class ConversionResultTransportTests(unittest.TestCase):
    def test_worker_never_writes_beyond_configured_limit(self):
        output = io.BytesIO()
        writer = BoundedResultWriter(output, 5)
        writer.write(b'123')
        with self.assertRaises(ResultLimitExceeded):
            writer.write(b'456')
        self.assertEqual(output.getvalue(), b'123')

    def test_worker_limit_exit_is_reported_with_recovery_setting(self):
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=74)):
            with self.assertRaisesRegex(ValueError, 'ENGINEERING_CONVERSION_MAX_RESULT_BYTES='):
                convert_engineering(filename='large.xsd', content=b'fixture')

    def worker(self, value):
        def run(*args, **kwargs):
            self.output = kwargs['stdout']
            self.errors = kwargs['stderr']
            self.assertNotIn('capture_output', kwargs)
            pickle.dump(value, self.output)
            return SimpleNamespace(returncode=0)
        return run

    def test_result_over_old_32_mib_limit_is_preserved_and_files_close(self):
        expected = {'ontology': {'turtle': 'a' * (33 * 1024 * 1024)}}
        with patch.dict(os.environ, {'ENGINEERING_CONVERSION_MAX_RESULT_BYTES': str(256 * 1024 * 1024)}), \
             patch('subprocess.run', side_effect=self.worker({'ok': True, 'result': expected})):
            result = convert_engineering(filename='large.xsd', content=b'fixture')
        self.assertEqual(result, expected)
        self.assertTrue(self.output.closed)
        self.assertTrue(self.errors.closed)

    def test_configured_limit_rejects_before_unpickling_and_closes_files(self):
        with patch.dict(os.environ, {'ENGINEERING_CONVERSION_MAX_RESULT_BYTES': '10'}), \
             patch('subprocess.run', side_effect=self.worker({'ok': True, 'result': 'too big'})), \
             patch('pickle.load') as load:
            with self.assertRaisesRegex(ValueError, 'ENGINEERING_CONVERSION_MAX_RESULT_BYTES=10'):
                convert_engineering(filename='large.xsd', content=b'fixture')
            load.assert_not_called()
        self.assertTrue(self.output.closed)

    def test_invalid_limits_fail_before_worker_launch(self):
        for value in ('0', '-1', '1073741825', 'invalid', '1.5'):
            with self.subTest(value=value), patch.dict(os.environ, {'ENGINEERING_CONVERSION_MAX_RESULT_BYTES': value}), \
                 patch('subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'must be an integer'):
                    convert_engineering(filename='large.xsd', content=b'fixture')
                run.assert_not_called()

    def test_worker_validation_error_is_retained(self):
        with patch('subprocess.run', side_effect=self.worker({'ok': False, 'message': 'Missing companion schema'})):
            with self.assertRaisesRegex(ValueError, 'Missing companion schema'):
                convert_engineering(filename='large.xsd', content=b'fixture')

    def test_truncated_result_reports_failure(self):
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=0)):
            with self.assertRaisesRegex(ValueError, 'incomplete result'):
                convert_engineering(filename='large.xsd', content=b'fixture')

    def test_worker_failure_cannot_return_a_conversion(self):
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(ValueError, 'worker failed'):
                convert_engineering(filename='large.xsd', content=b'fixture')
