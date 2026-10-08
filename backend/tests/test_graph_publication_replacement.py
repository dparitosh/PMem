"""Exercise the real RDF publisher against a recording transaction."""
import ast
import json
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from rdflib import Graph, Literal
from rdflib.compare import to_canonical_graph
from rdflib.namespace import OWL, RDF, RDFS


class PublicationReplacementTests(unittest.TestCase):
    def publisher(self):
        calls = []
        class Transaction:
            def run(self, query, **parameters):
                calls.append((query, parameters))
                return SimpleNamespace(consume=lambda: None)
        tx = Transaction()
        driver = SimpleNamespace(session=lambda **kw: nullcontext(SimpleNamespace(execute_write=lambda fn: fn(tx))))
        scope = dict(Graph=Graph, Literal=Literal, OWL=OWL, RDF=RDF, RDFS=RDFS,
                     to_canonical_graph=to_canonical_graph, json=json, datetime=datetime, timezone=timezone, Any=object)
        tree = ast.parse(Path('backend/graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        node = next(method for cls in tree.body if isinstance(cls, ast.ClassDef) for method in cls.body if getattr(method, 'name', '') == 'publish_turtle')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<publisher>', 'exec'), scope)
        publisher = SimpleNamespace(auth_mode='none', _driver=lambda: nullcontext(driver), database='test')
        return lambda content: scope['publish_turtle'](publisher, content=content, ontology_id='demo', prefix='d', publication_id='receipt'), calls

    def test_blank_nodes_have_stable_retry_identity(self):
        publish, calls = self.publisher()
        identities = []
        for _ in range(2):
            calls.clear()
            publish(b'[] <urn:part> [ <urn:name> "Part" ] .')
            identities.append(sorted(row['iri'] for query, args in calls if 'rows' in args and 'node.rdf_properties' in query for row in args['rows']))
        self.assertEqual(identities[0], identities[1])

    def test_replacement_removes_projection_edges_and_preserves_external_identity(self):
        publish, calls = self.publisher()
        publish(b'<urn:a> <urn:p> <urn:b> .')
        queries = [query for query, args in calls]
        self.assertTrue(any('DELETE edge' in query and 'edge.ontology_id = $ontology_id' in query for query in queries))
        self.assertTrue(any('REMOVE node:OntologyResource' in query for query in queries))
        self.assertTrue(any('WHERE NOT (node)--() DELETE node' in query for query in queries))
        self.assertFalse(any('DETACH DELETE' in query for query in queries))
        self.assertTrue(any('receipt.current = false' in query for query in queries))
        self.assertTrue(any('ON CREATE SET receipt.published_at' in query for query in queries))
