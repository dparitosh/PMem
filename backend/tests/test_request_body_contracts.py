"""Request schema coverage and malformed input regressions without live stores."""
import ast
import json
import unittest
from pathlib import Path
from pydantic import TypeAdapter, ValidationError
from backend.depo_platform import request_bodies as bodies

class RequestBodyContracts(unittest.TestCase):
    def test_all_named_body_schemas_compile(self):
        for name, cls in vars(bodies).items():
            if isinstance(cls, type) and cls.__module__ == bodies.__name__ and hasattr(cls, '__required_keys__'):
                with self.subTest(schema=name):
                    self.assertEqual(TypeAdapter(cls).json_schema()['type'], 'object')

    def test_inventory_has_no_unstructured_route_body(self):
        inventory = json.loads(Path('docs/audits/api-crud-inventory-2026-10-10.json').read_text())
        for route in inventory['routes']:
            tree = ast.parse(Path(route['file']).read_text(encoding='utf-8-sig'))
            handler = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == route['handler'])
            for parameter in handler.args.args:
                if parameter.annotation:
                    self.assertFalse(ast.unparse(parameter.annotation).startswith(('dict', 'Dict')), (route['file'], handler.name))

    def test_booleans_never_coerce_strings_or_numbers(self):
        for model, field in [(bodies.BrowserSessionBody, 'include_writes'), (bodies.QualityGateBody, 'deduplicate'), (bodies.MergeApplyBody, 'publish'), (bodies.ReportBody, 'include_documents')]:
            adapter = TypeAdapter(model)
            for value in ('false', 'true', 0, 1, None, [], {}):
                with self.subTest(model=model.__name__, value=value), self.assertRaises(ValidationError):
                    adapter.validate_python({field: value})
            self.assertEqual(adapter.validate_python({field: False})[field], False)

    def test_optional_fields_remain_absent_and_extensions_survive(self):
        payload = {'workflow_id': 'review', 'inputs': {'custom_format': 'qif'}, 'client_request_id': 'request-1'}
        self.assertEqual(TypeAdapter(bodies.WorkflowRunBody).validate_python(payload), payload)
        self.assertEqual(TypeAdapter(bodies.BrowserSessionBody).validate_python({}), {})

    def test_required_fields_are_described_and_validated(self):
        schema = TypeAdapter(bodies.NamespaceBody).json_schema()
        self.assertEqual(set(schema['required']), {'prefix', 'uri'})
        for payload in ({}, {'prefix': 'qif'}, {'prefix': 7, 'uri': 'urn:qif'}):
            with self.assertRaises(ValidationError): TypeAdapter(bodies.NamespaceBody).validate_python(payload)

    def test_nested_mappings_reject_malformed_rows(self):
        adapter = TypeAdapter(bodies.MergePreviewBody)
        for payload in [{'source_ontology_ids': 'qif'}, {'source_ontology_ids': ['qif']}, {'source_ontology_ids': ['qif', 'ap242'], 'entity_mappings': [{'source_iri': 'urn:source'}]}]:
            with self.assertRaises(ValidationError): adapter.validate_python(payload)
        value = {'source_ontology_ids': ['qif', 'ap242'], 'entity_mappings': [{'source_iri': 'urn:source', 'target_iri': 'urn:target'}]}
        self.assertEqual(adapter.validate_python(value), value)

    def test_nullable_ceim_publication_options_remain_compatible(self):
        value = {'entities': [], 'relationships': [], 'representation': None, 'ceim_version': None, 'resolution_case_ids': None, 'ontology_id': None}
        self.assertEqual(TypeAdapter(bodies.CeimBatchBody).validate_python(value), value)

    def test_inference_flags_and_limits_match_domain_validator(self):
        for value in ({'rules': {'unknown_rule': True}}, {'rules': {'equivalence': 'false'}}, {'limit': True}, {'limit': 24}, {'limit': 1001}):
            with self.assertRaises(ValidationError): TypeAdapter(bodies.InferenceBody).validate_python(value)

    def test_graphql_variables_and_schedule_containers_are_strict(self):
        for model, value in [(bodies.GraphQLBody, {'query': '{ health }', 'variables': []}), (bodies.ScheduleBody, {'replay_run_id': 'run-1', 'interval_seconds': True}), (bodies.SemanticWorkflowBody, {'workflow_id': 'review', 'payload': 'bad'})]:
            with self.assertRaises(ValidationError): TypeAdapter(model).validate_python(value)

    def test_live_contract_gate_rejects_stale_unstructured_bodies(self):
        from backend.depo_platform.openapi_contract import contract_errors, normalize_openapi
        document = {'openapi': '3.0.3', 'paths': {'/run': {'post': {'operationId': 'run', 'requestBody': {'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Body'}}}}}}}, 'components': {'schemas': {'Body': {'type': 'object', 'additionalProperties': True}}}}
        self.assertTrue(any('named fields' in error for error in contract_errors(normalize_openapi(document))))
        document['components']['schemas']['Body'] = TypeAdapter(bodies.WorkflowRunBody).json_schema()
        self.assertEqual(contract_errors(normalize_openapi(document)), [])
        document['components']['schemas']['Body'] = TypeAdapter(bodies.SourceRecordBody).json_schema()
        self.assertEqual(contract_errors(normalize_openapi(document)), [])
        del document['components']['schemas']['Body']
        self.assertTrue(any('reference is missing' in error for error in contract_errors(normalize_openapi(document))))

    def test_analytics_product_readiness_accepts_existing_string_contract(self):
        payload = dict(name='Quality', domain='engineering', owner='owner', classification='internal', steward='owner', lifecycle_state='published', analytics_readiness='structural-data-loaded; business-metrics-not-defined')
        self.assertEqual(TypeAdapter(bodies.ProductMetadataBody).validate_python(payload), payload)

    def test_nested_retry_policy_rejects_boolean_integers(self):
        with self.assertRaises(ValidationError):
            TypeAdapter(bodies.ScheduleBody).validate_python({'replay_run_id': 'run-1', 'interval_seconds': 60, 'retry_policy': {'max_attempts': True, 'backoff_seconds': 30}})

    def test_bridge_signed_payload_remains_exact(self):
        payload = {'publication_id': 'pub-1', 'request_digest': 'digest', 'preview_id': 'preview', 'ontology_id': 'qif', 'rows': [{'candidate_id': 'c-1', 'import_id': 'i-1', 'import_row_key': 'r-1', 'ontology_class_element_id': 'n-1', 'target_ontology_type': 'Class', 'confidence': 1}]}
        validated = TypeAdapter(bodies.BridgePublicationBody).validate_python(payload)
        self.assertEqual(json.dumps(validated, sort_keys=True), json.dumps(payload, sort_keys=True))
        self.assertIs(type(validated['rows'][0]['confidence']), int)

if __name__ == '__main__': unittest.main()
