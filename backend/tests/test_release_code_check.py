import tempfile
import unittest
from pathlib import Path
from backend.depo_platform.release_code_check import check


class ReleaseCheckTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        (root/'backend/Services').mkdir(parents=True)
        (root/'backend/Services/xsd_semantics.py').write_text('def qualify_schema_types(): pass\ndef validate_xsd_schema_set(): pass\n')
        (root/'backend/Services/owl_xsd_engine.py').write_text('def _collect_simple_types(paths, schema_roots=None): pass\n')
        return root

    def test_fingerprint_changes_when_backend_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            before = check(root)['backend_fingerprint']
            (root/'backend/new_service.py').write_text('value = 1\n')
            self.assertNotEqual(before, check(root)['backend_fingerprint'])

    def test_old_semantics_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root/'backend/Services/xsd_semantics.py').write_text('def inspect_conversion_schemas(): pass\n')
            with self.assertRaisesRegex(ValueError, 'Outdated'):
                check(root)

    def test_mixed_engine_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root/'backend/Services/owl_xsd_engine.py').write_text('def _collect_simple_types(paths): pass\n')
            with self.assertRaisesRegex(ValueError, 'Mixed converter'):
                check(root)
