import unittest
from backend.depo_platform.openapi_contract import normalize_openapi, contract_errors


class OptionalBodyTests(unittest.TestCase):
    def document(self, target):
        return {'openapi': '3.1.0', 'components': {'schemas': {'Payload': target}},
                'paths': {'/operation': {'post': {'operationId': 'operation',
                    'requestBody': {'content': {'application/json': {'schema': {
                        'anyOf': [{'$ref': '#/components/schemas/Payload'}, {'type': 'null'}]}}}}}}}}

    def test_optional_named_body_passes_after_normalization(self):
        doc = normalize_openapi(self.document({'type': 'object', 'properties': {'confirm': {'type': 'string'}}}))
        self.assertEqual(contract_errors(doc), [])
        schema = doc['paths']['/operation']['post']['requestBody']['content']['application/json']['schema']
        self.assertTrue(schema['nullable'])
        self.assertIn('allOf', schema)

    def test_optional_untyped_body_still_fails(self):
        doc = normalize_openapi(self.document({'type': 'object'}))
        self.assertTrue(any('needs named fields' in error for error in contract_errors(doc)))

    def test_optional_missing_reference_still_fails(self):
        doc = normalize_openapi(self.document({'type': 'object', 'properties': {'project': {'type': 'string'}}}))
        doc['components']['schemas'].clear()
        self.assertTrue(any('reference is missing' in error for error in contract_errors(doc)))


if __name__ == '__main__':
    unittest.main()
