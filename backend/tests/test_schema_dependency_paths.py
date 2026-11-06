"""Exercise upload path checks without installing the service dependency stack."""
from pathlib import Path
import unittest
from backend.Services.schema_upload_paths import validate_schema_upload as validate


def schema(body=''):
    return ('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'+body+'</xs:schema>').encode()


class DependencyPathTests(unittest.TestCase):
    def test_nested_dependency_can_reference_uploaded_sibling(self):
        root = schema('<xs:include schemaLocation="types/part.xsd"/>')
        files = {'types/part.xsd': schema('<xs:include schemaLocation="../shared.xsd"/>'), 'shared.xsd': schema()}
        self.assertEqual(validate('root.xsd', root, files), files)

    def test_missing_dependency_identifies_file_and_required_path(self):
        with self.assertRaisesRegex(ValueError, "root.xsd: missing schema dependency 'types/part.xsd'"):
            validate('root.xsd', schema('<xs:include schemaLocation="types/part.xsd"/>'))

    def test_external_url_requires_local_companion_instead_of_network_fetch(self):
        with self.assertRaisesRegex(ValueError, "external schemaLocation.*Upload 'common.xsd'"):
            validate('bom.xsd', schema('<xs:import schemaLocation="https://standards.example/common.xsd"/>'))

    def test_escape_remains_rejected(self):
        with self.assertRaisesRegex(ValueError, 'root.xsd: schemaLocation escapes'):
            validate('root.xsd', schema('<xs:include schemaLocation="../outside.xsd"/>'))

    def test_windows_absolute_path_remains_rejected(self):
        with self.assertRaisesRegex(ValueError, 'external schemaLocation|Windows filesystem path'):
            validate('root.xsd', schema('<xs:include schemaLocation="C:/schemas/common.xsd"/>'))

    def test_wrong_companion_root_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'part.xsd: expected an XML Schema root'):
            validate('root.xsd', schema('<xs:include schemaLocation="part.xsd"/>'), {'part.xsd': b'<document/>'})

    def test_case_mismatch_is_rejected_before_linux_resolution(self):
        with self.assertRaisesRegex(ValueError, 'missing schema dependency'):
            validate('root.xsd', schema('<xs:include schemaLocation="Common.xsd"/>'), {'common.xsd': schema()})

    def test_noncanonical_uploaded_paths_are_rejected(self):
        for name in ('types//part.xsd', './part.xsd', 'part%20name.xsd', 'part?.xsd', 'part#.xsd'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'distinct relative'):
                validate('root.xsd', schema(), {name: schema()})

    def test_uri_suffixes_and_encoding_are_rejected(self):
        for location in ('part.xsd?version=1', 'part.xsd#schema', 'part%20name.xsd'):
            with self.subTest(location=location), self.assertRaisesRegex(ValueError, 'literal relative'):
                validate('root.xsd', schema('<xs:include schemaLocation="'+location+'"/>'))

    def test_malformed_xml_has_safe_validation_error(self):
        with self.assertRaisesRegex(ValueError, 'malformed or unsafe'):
            validate('root.xsd', b'<xs:schema')

    def test_non_xsd_root_cannot_carry_companions(self):
        with self.assertRaisesRegex(ValueError, 'require an XSD root'):
            validate('root.xml', b'<document/>', {'part.xsd': schema()})

    def test_bundled_bom_requires_and_accepts_matching_local_common_schema(self):
        source = Path(__file__).resolve().parents[2] / 'data/business_object_models/managed_model_based_3d_engineering/bom.xsd'
        with self.assertRaisesRegex(ValueError, "bom.xsd: missing schema dependency 'common.xsd'"):
            validate(source.name, source.read_bytes())
        dependencies = {'common.xsd': source.with_name('common.xsd').read_bytes()}
        self.assertEqual(validate(source.name, source.read_bytes(), dependencies), dependencies)


if __name__ == '__main__':
    unittest.main()
