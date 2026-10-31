"""Semantic projection identity and trust-boundary regression coverage."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
from backend.data_pipeline_service.semantic_datasets import parse_records, resolve_source, validate_semantics
from backend.artifact_store import ArtifactStore

DATA = b'''@prefix a: <urn:a:> . @prefix b: <urn:b:> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
a:Part a owl:Class . b:Part a owl:Class .
a:p a a:Part ; a:mass "2.5"^^xsd:decimal ; a:name "Part"@en, "Piece"@fr .
b:p a b:Part ; a:mass "unknown" .'''

class SemanticRecords(unittest.TestCase):
    def test_identity_types_multivalues_and_numeric_literals(self):
        graph, terms, facts = parse_records(DATA, 'turtle')
        indexed = {term[0]: term for term in terms}
        self.assertEqual(indexed['urn:a:Part'][4], 'class')
        self.assertEqual(indexed['urn:a:p'][4], 'individual')
        self.assertNotEqual(indexed['urn:a:p'][1], indexed['urn:b:p'][1])
        names = [row for row in facts if row[2] == 'urn:a:name']
        self.assertEqual({row[6] for row in names}, {'en', 'fr'})
        numbers = [row for row in facts if row[2] == 'urn:a:mass']
        self.assertEqual(sum(row[7] is not None for row in numbers), 1)
        self.assertEqual(len(facts), len(graph))

    def test_xml_entities_and_remote_jsonld_context_are_rejected(self):
        for content, fmt in [(b'<!DOCTYPE rdf [<!ENTITY x SYSTEM "file:///secret">]><rdf/>', 'xml'),
                             (b'{"@context":"https://example.org/context","@id":"urn:a"}', 'json-ld')]:
            with self.subTest(fmt=fmt), self.assertRaises(ValueError):
                parse_records(content, fmt)

    def test_registered_source_ownership_is_required(self):
        registry = Mock(); registry.get.return_value = {'artifacts':[{'artifact_id':'sha256:owned'}]}
        with patch('backend.data_pipeline_service.semantic_datasets.PostgresRegistry', return_value=registry):
            with self.assertRaisesRegex(ValueError, 'does not belong'):
                resolve_source('catalog:parts:1.0.0', 'sha256:foreign')
            resolve_source('catalog:parts:1.0.0', 'sha256:owned')

    def test_large_identifier_fails_before_database_index_write(self):
        with self.assertRaisesRegex(ValueError, 'indexed'):
            parse_records(('<urn:'+ 'a'*900 + '> <urn:p> "v" .').encode(), 'nt')

    def test_semantica_shapes_and_unassessed_scope_are_explicit(self):
        graph, _, _ = parse_records(DATA, 'turtle')
        self.assertEqual(validate_semantics(graph, {})['status'], 'not_assessed')
        with tempfile.TemporaryDirectory() as temporary:
            store=ArtifactStore(Path(temporary))
            shapes=b'''@prefix sh: <http://www.w3.org/ns/shacl#> .
            <urn:Shape> a sh:NodeShape; sh:targetClass <urn:a:Part>;
            sh:property [sh:path <urn:a:name>; sh:minCount 1] .'''
            rules=store.ingest_bytes(shapes,filename='rules.ttl')
            with patch('backend.data_pipeline_service.semantic_datasets.ArtifactStore',return_value=store), patch('backend.data_pipeline_service.semantic_datasets.resolve_source',return_value={}):
                result=validate_semantics(graph,{'source_id':'metadata:rules','shape_artifact_id':rules['artifact_id']})
                self.assertEqual(result['status'],'conforms')
                rules=store.ingest_bytes(shapes.replace(b'minCount 1',b'minCount 3'),filename='strict.ttl')
                with self.assertRaisesRegex(ValueError,'SHACL checks failed'):
                    validate_semantics(graph,{'source_id':'metadata:rules','shape_artifact_id':rules['artifact_id']})
