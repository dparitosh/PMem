import tempfile
import ast
import unittest
import zipfile
from pathlib import Path
from backend.data_product_service.packaging import build_package, verify_package


class ProductPackageIntegrity(unittest.TestCase):
    def test_public_records_hide_legacy_catalog_exception_details(self):
        tree = ast.parse(Path('backend/data_product_service/router.py').read_text(encoding='utf-8'))
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_public_product')
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'router.py', 'exec'), namespace)
        public = namespace['_public_product']({'product_id':'product', 'catalog_error':'private-host/query/credential', 'package_storage':{}})
        self.assertNotIn('private-host', public['catalog_error'])
        self.assertNotIn('package_storage', public)

    def test_delivery_verification_rejects_changed_content_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.txt'; source.write_text('immutable evidence')
            payload = {'product_id':'product', 'version':'1.0.0', 'name':'Evidence', 'domain':'engineering', 'owner':'steward'}
            artifact = {'artifact_id':'sha256:'+'a'*64}
            package = build_package(output_root=root, payload=payload, artifacts=[(artifact, source)])
            args = (package['package_dir'], package['zip_path'], package['manifest'])
            self.assertEqual(verify_package(*args), package['manifest'])
            with self.assertRaises(ValueError): verify_package(args[0], args[1], {'unexpected':True})
            retained = package['package_dir'] / package['manifest']['artifacts'][0]['package_path']
            retained.write_text('changed evidence')
            with self.assertRaises(ValueError): verify_package(*args)

    def test_delivery_verification_rejects_corrupt_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.txt'; source.write_text('evidence')
            payload = {'product_id':'product', 'version':'1.0.0', 'name':'Evidence', 'domain':'engineering', 'owner':'steward'}
            package = build_package(output_root=root, payload=payload, artifacts=[({'artifact_id':'sha256:'+'a'*64}, source)])
            package['zip_path'].write_bytes(b'corrupt ZIP')
            with self.assertRaises(ValueError): verify_package(package['package_dir'], package['zip_path'], package['manifest'])
