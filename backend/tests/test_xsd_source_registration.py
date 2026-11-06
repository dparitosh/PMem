import ast
import logging
from pathlib import Path
from typing import Any, Dict
import unittest


class SourceRegistrationTests(unittest.TestCase):
    def test_source_registration_does_not_require_referenced_schemas(self):
        tree = ast.parse(Path('backend/Services/ontology_upload_manager.py').read_text(encoding='utf-8'))
        function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == '_materialize_semantic_artifacts')
        function.decorator_list = []
        scope = dict(Path=Path, Any=Any, Dict=Dict, logger=logging.getLogger('source-test'))
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<source>', 'exec'), scope)
        result = scope[function.name](None, Path('.'), Path('sample.xsd'),
            b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:example"><xs:import namespace="urn:missing" schemaLocation="https://example.test/missing.xsd"/></xs:schema>',
            'sample.xsd', 'xsd', 'as_is')
        self.assertEqual(result['semantic_artifacts_status'], 'source_registered')
        self.assertEqual(result['owl_file_path'], '')
        self.assertTrue(result['ontology_export_artifacts'][0]['source'])


if __name__ == '__main__':
    unittest.main()
