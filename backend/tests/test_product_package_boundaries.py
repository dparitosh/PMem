import tempfile
import unittest
from pathlib import Path
from backend.data_product_service.packaging import build_package

class PackageBoundaries(unittest.TestCase):
    def test_oversized_manifest_is_rejected_without_visible_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'source.txt'; source.write_text('evidence')
            payload={'product_id':'large','version':'1.0.0','name':'Large','domain':'test','owner':'test','description':'x'*(8*1024*1024)}
            with self.assertRaisesRegex(ValueError,'manifest exceeds'):
                build_package(output_root=root,payload=payload,artifacts=[({'artifact_id':'sha256:abc'},source)])
            self.assertFalse((root/'packages/large/1.0.0').exists())

    def test_changed_source_during_copy_is_rejected(self):
        from unittest.mock import patch
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'source.txt'; source.write_text('original')
            copy=shutil.copy2
            def changed(source_path,target):
                source_path.write_text('changed'); return copy(source_path,target)
            payload={'product_id':'changed','version':'1.0.0','name':'Changed','domain':'test','owner':'test'}
            with patch('backend.data_product_service.packaging.shutil.copy2',changed), self.assertRaisesRegex(ValueError,'source changed'):
                build_package(output_root=root,payload=payload,artifacts=[({'artifact_id':'sha256:abc'},source)])
            self.assertFalse((root/'packages/changed/1.0.0').exists())

    def test_existing_package_rejects_changed_metadata_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.txt'; source.write_text('original')
            payload = {'product_id':'quality','version':'1.0.0','name':'Quality','domain':'engineering','owner':'steward'}
            artifacts = [({'artifact_id':'sha256:abc'}, source)]
            first = build_package(output_root=root, payload=payload, artifacts=artifacts)
            second = build_package(output_root=root, payload=payload, artifacts=artifacts)
            self.assertEqual(first['manifest'], second['manifest'])
            with self.assertRaises(ValueError):
                build_package(output_root=root, payload={**payload, 'name':'Changed'}, artifacts=artifacts)
            source.write_text('changed')
            with self.assertRaises(ValueError):
                build_package(output_root=root, payload=payload, artifacts=artifacts)
    def test_unsafe_identifiers_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for product, version in (('../outside','1.0.0'),('product','../../outside'),('C:/escape','1.0.0')):
                with self.subTest(product=product,version=version), self.assertRaises(ValueError):
                    build_package(output_root=root,payload={'product_id':product,'version':version},artifacts=[])
            self.assertEqual(list(root.iterdir()),[])

    def test_corrupt_archive_cannot_be_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.txt'; source.write_text('evidence')
            payload = {'product_id':'quality','version':'1.0.0','name':'Quality','domain':'engineering','owner':'steward'}
            artifacts = [({'artifact_id':'sha256:abc'}, source)]
            result = build_package(output_root=root, payload=payload, artifacts=artifacts)
            result['zip_path'].write_bytes(b'truncated')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                build_package(output_root=root, payload=payload, artifacts=artifacts)

    def test_modified_packaged_artifact_cannot_be_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.txt'; source.write_text('evidence')
            payload = {'product_id':'quality','version':'1.0.0','name':'Quality','domain':'engineering','owner':'steward'}
            artifacts = [({'artifact_id':'sha256:abc'}, source)]
            result = build_package(output_root=root, payload=payload, artifacts=artifacts)
            (result['package_dir'] / 'artifacts/abc').write_text('corrupt')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                build_package(output_root=root, payload=payload, artifacts=artifacts)

    def test_valid_package_contains_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_package(output_root=Path(directory),payload={'product_id':'quality-product','version':'1.0.0','name':'Quality','domain':'engineering','owner':'steward'},artifacts=[])
            self.assertTrue(result['zip_path'].is_file())
            self.assertEqual(result['manifest']['product_id'],'quality-product')

if __name__ == '__main__': unittest.main()
