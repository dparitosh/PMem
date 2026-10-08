import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid
from datetime import datetime, timezone
from rdflib import Graph, Literal, BNode, URIRef, RDF, OWL, RDFS

class MergeEntityChangesTests(unittest.TestCase):
    def service(self, incompatible=False):
        tree = ast.parse(Path('backend/ontology_service/merge_service.py').read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        scope = dict(globals(), Any=object, __package__='backend.ontology_service')
        exec(compile(ast.Module(body=[cls], type_ignores=[]), '<merge>', 'exec'), scope)
        service = scope['GovernedMergeService'].__new__(scope['GovernedMergeService'])
        first = b'@prefix ex: <urn:ex:> . @prefix owl: <http://www.w3.org/2002/07/owl#> . ex:Part a owl:Class . ex:item ex:uses ex:Part .'
        second = b'@prefix ex: <urn:ex:> . @prefix owl: <http://www.w3.org/2002/07/owl#> . ex:Component a owl:Class .'
        if incompatible: second = second.replace(b'owl:Class', b'owl:ObjectProperty')
        service.catalog = SimpleNamespace(get=lambda key: {}, read_artifact=lambda key: ({'ontology_name': key, 'original_filename': 'source.ttl'}, first if key == 'a' else second), _parse_ontology=lambda *args: {'rdf_format': 'turtle'})
        service.registry = None; service._load = lambda: {}; service._save = lambda *args: None
        return service

    def test_reviewed_mapping_rewrites_references_and_reports_exact_delta(self):
        result = self.service()._preview({'source_ontology_ids': ['a', 'b'], 'entity_mappings': [{'source_iri': 'urn:ex:Part', 'target_iri': 'urn:ex:Component'}]})
        changes = result['changes']
        self.assertEqual(changes['modified_entity_count'], 1)
        self.assertEqual(changes['unchanged'], 1)
        self.assertEqual(changes['added'], 1)
        self.assertEqual(changes['removed'], 0)
        self.assertIn('<urn:ex:Component>', changes['added_sample'][0])
        self.assertNotIn('<urn:ex:Part>', changes['added_sample'][0])
        self.assertEqual(result['duplicate_triple_count'], 0)
        self.assertEqual(result['consolidated_triple_count'], 1)

    def test_incompatible_entity_kinds_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'same kind'):
            self.service(True)._preview({'source_ontology_ids': ['a', 'b'], 'entity_mappings': [{'source_iri': 'urn:ex:Part', 'target_iri': 'urn:ex:Component'}]})
