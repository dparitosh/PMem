"""Verify the real legacy pipeline gate before enrichment and graph writes."""
import ast
import asyncio
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class ImportShaclGateTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'Services/data_import_service.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == '_validate_stage')
        function.decorator_list = []
        self.task = {'stats': {}}
        scope = {'Dict': dict, 'Any': object, 'import_tasks': {'task': self.task}, '__package__': 'backend.Services'}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
        self.validate = scope['_validate_stage']
        self.module = ModuleType('backend.Services.owl_generation_service')

    def run_gate(self, payload, report):
        self.module.OWLGenerationService = SimpleNamespace(validate_with_shacl=lambda *a, **k: report)
        with patch.dict(sys.modules, {'backend.Services.owl_generation_service': self.module}):
            return asyncio.run(self.validate(object(), 'task', payload))

    def test_failure_blocks_and_retains_report(self):
        with self.assertRaisesRegex(ValueError, 'ingestion is blocked'):
            self.run_gate({'rdf_ttl': 'data', 'shacl_shapes': 'shapes'}, {'conforms': False, 'violation_count': 1})
        self.assertEqual(self.task['stats']['validation_status'], 'failed')
        self.assertEqual(self.task['shacl_report']['validation_scope'], 'instance')

    def test_missing_artifact_is_not_success(self):
        with self.assertRaisesRegex(ValueError, 'No RDF'):
            self.run_gate({'entities': [{}]}, {'conforms': True})
        self.assertEqual(self.task['stats']['validation_status'], 'unavailable')

    def test_generated_ontology_does_not_claim_instance_validation(self):
        self.task['owl_ttl'] = 'ontology'
        result = self.run_gate({}, {'conforms': True})
        self.assertEqual(result['validation_scope'], 'ontology')

    def test_parse_error_blocks_even_with_validator_success(self):
        with self.assertRaisesRegex(ValueError, 'Source parsing failed'):
            self.run_gate({'error': 'invalid XML', 'rdf_ttl': 'data'}, {'conforms': True})


if __name__ == '__main__': unittest.main()
