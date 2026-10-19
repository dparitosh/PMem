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
             patch('pyshacl.validate', return_value=(True, Graph(), 'Conforms')) as validate:
            result = _validate_merge(Graph(), [{'engineering_artifacts': {'shacl': 'sha256:test'}}])
        self.assertTrue((URIRef('urn:shape'), RDF.type, SH.NodeShape) in validate.call_args.kwargs['shacl_graph'])
        self.assertEqual(validate.call_args.kwargs['inference'], 'owlrl')
        self.assertTrue(result['shacl_conforms'])
        self.assertEqual(result['shape_sources'], ['sha256:test'])

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
            with patch('pyshacl.validate', return_value=(True, Graph(), 'Conforms')) as validate:
                _validate_merge(Graph(), [{'shacl_file_path': str(path)}])
            self.assertTrue((URIRef('urn:shape'), RDF.type, SH.NodeShape) in validate.call_args.kwargs['shacl_graph'])

    def test_supported_metadata_does_not_accept_malformed_rdf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'content'
            path.write_bytes(b'This is not Turtle')
            with patch('backend.artifact_store.ArtifactStore.resolve', return_value=({'filename': 'shapes.ttl'}, path)), \
                 patch('pyshacl.validate') as validate:
                with self.assertRaisesRegex(ValueError, 'parsing failed'):
                    _validate_merge(Graph(), [{'engineering_artifacts': {'shacl': 'sha256:test'}}])
                validate.assert_not_called()

if __name__ == '__main__': unittest.main()
