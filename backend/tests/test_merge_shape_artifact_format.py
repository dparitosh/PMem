import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from rdflib import Graph, RDF, URIRef
from rdflib.namespace import SH
from backend.ontology_service.merge_semantics import _validate_merge

SHAPES = b'@prefix sh: <http://www.w3.org/ns/shacl#> . <urn:shape> a sh:NodeShape; sh:targetNode <urn:entity> .'

class MergeShapeArtifactFormatTests(unittest.TestCase):
    def run_validation(self, metadata):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'content'
        path.write_bytes(SHAPES)
        with patch('backend.artifact_store.ArtifactStore.resolve', return_value=(metadata, path)), \
             patch('backend.ontology_service.merge_reporting.validate_shacl', return_value=(True, Graph(), 'Conforms', {})) as validate:
            result = _validate_merge(Graph(), [{'engineering_artifacts': {'shacl': 'sha256:test'}}])
        self.assertTrue(any((URIRef('urn:shape'), RDF.type, SH.NodeShape) in call.kwargs['shacl_graph'] for call in validate.call_args_list))
        self.assertTrue(result['owl_rl_performed'])
        self.assertTrue(result['shacl_conforms'])
        self.assertIn('sha256:test', result['shape_sources'])
        self.assertIn('default ontology checks', result['shape_sources'])

    def test_extensionless_content_uses_retained_filename(self):
        self.run_validation({'filename': 'AP242_shapes.ttl', 'media_type': 'text/turtle'})

    def test_extensionless_filename_uses_known_media_type(self):
        self.run_validation({'filename': 'content', 'media_type': 'text/turtle; charset=utf-8'})

    def test_unknown_format_does_not_skip_shape_validation(self):
        with self.assertRaisesRegex(ValueError, 'supported RDF format metadata'):
            self.run_validation({'filename': 'content', 'media_type': 'application/octet-stream'})

    def test_legacy_shape_file_path_still_loads_shapes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'shapes.ttl'
            path.write_bytes(SHAPES)
            with patch('backend.ontology_service.merge_reporting.validate_shacl', return_value=(True, Graph(), 'Conforms', {})) as validate:
                _validate_merge(Graph(), [{'shacl_file_path': str(path)}])
            self.assertTrue(any((URIRef('urn:shape'), RDF.type, SH.NodeShape) in call.kwargs['shacl_graph'] for call in validate.call_args_list))

    def test_supported_metadata_does_not_accept_malformed_rdf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'content'
            path.write_bytes(b'This is not Turtle')
            with patch('backend.artifact_store.ArtifactStore.resolve', return_value=({'filename': 'shapes.ttl'}, path)), \
                 patch('backend.ontology_service.merge_reporting.validate_shacl') as validate:
                with self.assertRaisesRegex(ValueError, 'parsing failed'):
                    _validate_merge(Graph(), [{'engineering_artifacts': {'shacl': 'sha256:test'}}])
                validate.assert_not_called()

    def test_retained_generated_editorial_rules_match_inline_rules_after_inference(self):
        from backend.Services.shacl_service import ShaclValidationService
        graph = Graph().parse(data='''@prefix owl:<http://www.w3.org/2002/07/owl#> .
            @prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> .
            @prefix dc:<http://purl.org/dc/elements/1.1/> .
            <urn:Part> a owl:Class; rdfs:label "Part"; rdfs:comment "Definition"; dc:source "fixture" .''', format='turtle')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'shapes.ttl'
            path.write_text(ShaclValidationService().create_default_shapes(), encoding='utf-8')
            retained = _validate_merge(graph, [{'shacl_file_path': str(path)}])
            inline = _validate_merge(graph, [])
        self.assertTrue(retained['shacl_conforms'])
        self.assertEqual(retained['shacl_conforms'], inline['shacl_conforms'])
        self.assertTrue(retained['owl_rl_performed'])

    def test_custom_rule_keeps_inferred_target_semantics(self):
        from rdflib.namespace import OWL
        custom = '''@prefix sh:<http://www.w3.org/ns/shacl#> .
            @prefix owl:<http://www.w3.org/2002/07/owl#> .
            <urn:custom> a sh:NodeShape; sh:targetClass owl:Class;
            sh:property [ sh:path <urn:required>; sh:minCount 1 ] .'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.ttl'; path.write_text(custom, encoding='utf-8')
            with patch('backend.ontology_service.merge_reporting.validate_shacl', return_value=(False, Graph(), 'Custom constraint failed', {})) as validate:
                result = _validate_merge(Graph(), [{'shacl_file_path':str(path)}])
        rules = next(call.kwargs['shacl_graph'] for call in validate.call_args_list if (URIRef('urn:custom'), RDF.type, SH.NodeShape) in call.kwargs['shacl_graph'])
        self.assertTrue(list(rules.triples((None,SH.targetClass,OWL.Class))))
        self.assertFalse(result['shacl_conforms'])

if __name__ == '__main__': unittest.main()
