import unittest
from unittest.mock import patch
from backend.depo_platform.ontology_namespace import ontology_prefix
from backend.Services.owl_generation_service import _derive_prefix_from_namespace
from backend.Services.schema_upload_paths import validate_schema_upload

class OntologyUploadCleanupTests(unittest.TestCase):
    def test_namespace_tokens_have_no_vendor_aliases(self):
        for uri, expected in [('http://www.plmxml.org/Schemas/PLMXMLSchema#', 'plmxmlschema'), ('urn:iso:AP242', 'ap242'), ('https://example.org/model#42-items', 'ns_42_items'), ('https://example.org/Other', 'other')]:
            with self.subTest(uri=uri):
                self.assertEqual(ontology_prefix(uri), expected)
                self.assertEqual(_derive_prefix_from_namespace(uri), expected)
        self.assertEqual(ontology_prefix(''), 'ontology')

    def test_schema_set_obeys_configured_lower_limit(self):
        source = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'
        with patch.dict('os.environ', {'ONTOLOGY_MAX_UPLOAD_BYTES': '10'}):
            with self.assertRaises(ValueError):
                validate_schema_upload('source.xsd', source)

if __name__ == '__main__': unittest.main()
