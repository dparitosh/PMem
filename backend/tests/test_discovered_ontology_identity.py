"""Check discovery identities without requiring the ingestion runtime."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

class DiscoveryIdentityTests(unittest.TestCase):
    def entry(self, row):
        tree = ast.parse(Path('backend/Services/ontology_upload_manager.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_neo4j_only_entry')
        method.decorator_list = []
        scope = {'Dict': dict, 'Any': object, 'OntologyUploadManager': SimpleNamespace(_availability=lambda *args: 'available')}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<discovery>', 'exec'), scope)
        return scope['_neo4j_only_entry'](row)

    def test_published_graph_keeps_catalog_identity(self):
        self.assertEqual(self.entry({'prefix':'splm','ontology_id':'splm_123'})['ontology_id'], 'splm_123')

    def test_unidentified_graph_keeps_prefix_identity(self):
        self.assertEqual(self.entry({'prefix':'splm','ontology_id':None})['ontology_id'], 'splm')

    def test_distinct_registrations_are_not_collapsed_by_prefix(self):
        self.assertNotEqual(self.entry({'prefix':'splm','ontology_id':'a'})['ontology_id'],
                            self.entry({'prefix':'splm','ontology_id':'b'})['ontology_id'])
