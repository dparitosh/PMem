"""Dependency-light regression checks of actual native artifact adapters."""
import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, Dict
import unittest

ROOT = Path(__file__).resolve().parents[2]


def method(path, name, metadata):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8-sig'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    node.body = [n for n in node.body if not isinstance(n, ast.ImportFrom)]
    namespace = dict(Path=Path, Any=Any, Dict=Dict,
                     OntologyTaxonomyService=SimpleNamespace(_resolve_metadata=lambda _: metadata))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), path, 'exec'), namespace)
    return namespace[name]


class NativeContextTests(unittest.TestCase):
    def test_native_context_retains_artifact_and_identity(self):
        with TemporaryDirectory() as directory:
            artifact = Path(directory) / 'ontology.ttl'
            artifact.write_text('@prefix owl: <http://www.w3.org/2002/07/owl#> .', encoding='utf-8')
            metadata = dict(ontology_id='splm_123', prefix='splm', artifact_path=str(artifact))
            context = method('backend/ontology_service/domain/reasoning.py', 'semantic_context', metadata)(None, 'splm')
            self.assertEqual(context['file_path'], artifact)
            self.assertEqual(context['meta']['ontology_id'], 'splm_123')
            adapted = method('backend/Services/semantic_workflow_service.py', '_ontology_metadata', metadata)('splm')
            self.assertEqual(adapted['file_path'], str(artifact))
            self.assertNotIn('file_path', metadata)

    def test_missing_native_artifact_is_rejected(self):
        metadata = dict(ontology_id='missing', artifact_path='/not/a/retained/ontology.ttl')
        with self.assertRaises(ValueError):
            method('backend/ontology_service/domain/reasoning.py', 'semantic_context', metadata)(None, 'missing')

    def test_dictionary_route_is_owned_by_ingestion(self):
        config = (ROOT / 'frontend/src/config.js').read_text(encoding='utf-8')
        route = next(line for line in config.splitlines() if 'taxonomy|reason|' in line)
        self.assertIn("['ingestion'", route)
        self.assertIn('data-dictionary', route)
