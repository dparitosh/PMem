"""Regression check for QIF sibling-folder dependencies."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from lxml import etree
from backend.tests.test_schema_dependency_paths import validate

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('prepare_xsd_upload', ROOT / 'infra/prepare-xsd-upload.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class BundleTests(unittest.TestCase):
    def test_qif_product_compiles_and_passes_upload_validation(self):
        source = ROOT / 'docs/xsd/QIFApplications/QIFProduct.xsd'
        original = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'bundle'
            files = bundle.prepare(source, ROOT / 'docs/xsd', output)
            root = files.pop(source.name)
            validate(source.name, root, files)
            from backend.Services.xsd_semantics import inspect_conversion_schemas, expand_model_groups
            paths = [output / source.name, *[output / name for name in files]]
            inspect_conversion_schemas(paths)
            from backend.Services.xsd_semantics import validate_xsd_schema_set
            validate_xsd_schema_set(output / source.name)
            expanded = expand_model_groups(paths)
            self.assertFalse(any(node.tag.endswith('}attributeGroup') for tree in expanded.values() for node in tree.iter()))
            etree.XMLSchema(etree.parse(str(output / source.name), etree.XMLParser(no_network=True, resolve_entities=False)))
            self.assertEqual(len(files), 11)
            with self.assertRaisesRegex(ValueError, 'existing files'):
                bundle.prepare(source, ROOT / 'docs/xsd', output)
        self.assertEqual(source.read_bytes(), original)

    def test_escape_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory) / 'schemas'
            boundary.mkdir()
            source = boundary / 'root.xsd'
            source.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="../outside.xsd"/></xs:schema>')
            output = Path(directory) / 'bundle'
            with self.assertRaisesRegex(ValueError, 'escapes'):
                bundle.prepare(source, boundary, output)
            self.assertFalse(output.exists())

    def test_duplicate_declarations_in_combined_set_fail_schema_validation(self):
        from backend.Services.xsd_semantics import validate_xsd_schema_set
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'entry.xsd').write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="one.xsd"/><xs:include schemaLocation="two.xsd"/></xs:schema>')
            text = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="Item" type="xs:string"/></xs:schema>'
            for name in ('one.xsd', 'two.xsd'):
                (root / name).write_text(text)
            with self.assertRaisesRegex(ValueError, 'schema-set validation failed'):
                validate_xsd_schema_set(root / 'entry.xsd')
