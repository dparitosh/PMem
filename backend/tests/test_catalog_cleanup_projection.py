import ast
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock


class CatalogCleanupTests(unittest.TestCase):
    def method(self):
        source = Path(__file__).resolve().parents[1] / 'ontology_service' / 'catalog.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'OntologyCatalog')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'clear_registration_metadata')
        scope = {'_safe_token': lambda value, **kw: value, 'logging': logging}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)
        return scope['clear_registration_metadata']

    def test_clears_registration_and_mirror_but_preserves_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'qif').mkdir()
            mirror = root / 'qif' / 'metadata.json'
            artifact = root / 'qif' / 'ontology.ttl'
            mirror.write_text('{}')
            artifact.write_text('retained evidence')
            catalog = MagicMock(root=root, _postgres_enabled=True)
            catalog.list.return_value = [{'ontology_id': 'qif'}]
            result = self.method()(catalog)
            catalog.list.assert_called_once_with(include_superseded=True)
            self.assertEqual(result['status'], 'success')
            self.assertFalse(mirror.exists())
            self.assertTrue(artifact.exists())
            cursor = catalog.registry._connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            self.assertEqual(cursor.execute.call_args.args[1], ('ontology_catalog', 'qif'))

    def test_targeted_cleanup_preserves_other_catalogs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for identifier in ('old_xsd', 'qif'):
                (root / identifier).mkdir()
                (root / identifier / 'metadata.json').write_text('{}')
            catalog = MagicMock(root=root, _postgres_enabled=True)
            catalog.list.return_value = [{'ontology_id': 'old_xsd'}, {'ontology_id': 'qif'}]
            result = self.method()(catalog, ['old_xsd'])
            self.assertEqual(result['cleared'], 1)
            self.assertTrue((root / 'qif' / 'metadata.json').exists())
            self.assertFalse((root / 'old_xsd' / 'metadata.json').exists())

    def test_failed_metadata_removal_preserves_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'qif').mkdir()
            # A directory at the metadata path cannot be silently unlinked.
            (root / 'qif' / 'metadata.json').mkdir()
            catalog = MagicMock(root=root, _postgres_enabled=True)
            catalog.list.return_value = [{'ontology_id': 'qif'}]
            with self.assertLogs(level='ERROR'):
                result = self.method()(catalog)
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['failed'], ['qif'])
            catalog.registry._connect.assert_not_called()

    def test_xsd_cleanup_returns_results_after_batches(self):
        source = Path(__file__).resolve().parents[1] / 'Services' / 'unified_import_router.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        handler = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'cleanup_old_xsd_schemas')
        self.assertIsInstance(handler.body[-1], ast.Return)
        self.assertIsInstance(handler.body[-1].value, ast.Dict)


if __name__ == '__main__':
    unittest.main()
