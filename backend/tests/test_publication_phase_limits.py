import ast
import io
import os
import pickle
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.depo_platform.network import graph_dispatch_timeout_seconds, ontology_publication_timeout_seconds


class PhaseTests(unittest.TestCase):
    def test_http_budget_covers_configured_write_and_activation(self):
        with patch.dict(os.environ, {'GRAPH_PUBLICATION_TIMEOUT_SECONDS':'180',
                'GRAPH_PUBLICATION_WRITE_TIMEOUT_SECONDS':'600', 'GRAPH_PUBLICATION_ACTIVATION_TIMEOUT_SECONDS':'300'}, clear=True):
            self.assertEqual(graph_dispatch_timeout_seconds(), 1110)
            self.assertEqual(ontology_publication_timeout_seconds(), 1320)

    def test_missing_staging_schema_cannot_silently_use_atomic_fallback(self):
        tree = ast.parse(Path('backend/graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_publish_staged_initial')
        queries = []
        def query(text, timeout):
            queries.append(timeout)
            return text
        scope = {'Query':query}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<publisher>', 'exec'), scope)
        with self.assertRaisesRegex(RuntimeError, 'schema is missing'):
            scope['_publish_staged_initial'](object(), SimpleNamespace(run=lambda q: SimpleNamespace(single=lambda: None)))
        self.assertEqual(queries, [10])

    def test_projection_rows_are_built_in_the_preparation_child(self):
        tree = ast.parse(Path('backend/depo_platform/rdf_preparation.py').read_text(encoding='utf-8'))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        output = io.BytesIO()
        projection = ([{'iri':'urn:a'}], {'HAS_PART':[]}, {})
        build = Mock(return_value=projection)
        graph = [('urn:a','urn:p','urn:b')]
        scope = {'pickle':pickle, 'sys': SimpleNamespace(stdin=SimpleNamespace(buffer=io.BytesIO(
            pickle.dumps((b'ttl','turtle','projection')))), stdout=SimpleNamespace(buffer=output))}
        with patch.dict('sys.modules', {'rdflib':SimpleNamespace(Graph=lambda:SimpleNamespace(parse=lambda **kw:graph),BNode=type('BNode',(),{})),
                'rdflib.compare':SimpleNamespace(to_canonical_graph=lambda value:value),
                'backend.depo_platform.projection_preparation':SimpleNamespace(build_projection=build)}):
            exec(compile(ast.Module(body=[main], type_ignores=[]), '<preparation>', 'exec'), scope)
            scope['main']()
        build.assert_called_once_with(graph)
        self.assertEqual(pickle.loads(output.getvalue()), projection)

    def test_receipt_and_resource_constraints_are_required_before_activation(self):
        from backend.depo_platform.neo4j_setup import CONSTRAINT_DEFINITIONS
        tree = ast.parse(Path('backend/graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_publish_staged_initial')
        scope = {'Query': lambda text, **kwargs: text}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<publisher>', 'exec'), scope)
        for missing in ('uq_ontologypublication_identity', 'uq_ontologyresource_identity'):
            calls = []
            def run(query):
                name = next(name for name in CONSTRAINT_DEFINITIONS if name in query)
                calls.append(name)
                label, properties = CONSTRAINT_DEFINITIONS[name]
                row = None if name == missing else {'type': 'UNIQUENESS', 'entityType': 'NODE',
                                                    'labelsOrTypes': [label], 'properties': properties}
                return SimpleNamespace(single=lambda: row)
            with self.subTest(missing=missing), self.assertRaisesRegex(RuntimeError, missing):
                scope['_publish_staged_initial'](object(), SimpleNamespace(run=run))
            self.assertEqual(calls[-1], missing)
