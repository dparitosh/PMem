import tempfile
import unittest
from pathlib import Path
from backend.data_product_service.packaging import build_package

class PackageBoundaries(unittest.TestCase):
    def test_unsafe_identifiers_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for product, version in (('../outside','1.0.0'),('product','../../outside'),('C:/escape','1.0.0')):
                with self.subTest(product=product,version=version), self.assertRaises(ValueError):
                    build_package(output_root=root,payload={'product_id':product,'version':version},artifacts=[])
            self.assertEqual(list(root.iterdir()),[])

    def test_valid_package_contains_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_package(output_root=Path(directory),payload={'product_id':'quality-product','version':'1.0.0','name':'Quality','domain':'engineering','owner':'steward'},artifacts=[])
            self.assertTrue(result['zip_path'].is_file())
            self.assertEqual(result['manifest']['product_id'],'quality-product')

if __name__ == '__main__': unittest.main()
