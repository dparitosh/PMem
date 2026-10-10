import unittest
from types import SimpleNamespace

try:
    from rdflib import Graph, URIRef
    from rdflib.namespace import RDF, RDFS
    from backend.oslc_service.representation import represent
except ImportError:
    represent = None


@unittest.skipIf(represent is None, 'RDFLib/FastAPI required for representation integration tests')
class OslcRepresentations(unittest.TestCase):
    def test_rdf_serializations_keep_members_and_predicates(self):
        payload = {'uri': 'urn:query', 'type': 'oslc:QueryResult', 'members': [
            {'uri': 'urn:item', 'rdf:type': ['urn:Class'], 'outgoingLinks': [
                {'predicate': 'urn:relation', 'targetUri': 'urn:target'}]}]}
        for media, serialization in [('text/turtle', 'turtle'), ('application/rdf+xml', 'xml'), ('application/ld+json', 'json-ld')]:
            with self.subTest(media=media):
                response = represent(payload, SimpleNamespace(headers={'accept': media}))
                graph = Graph().parse(data=response.body, format=serialization)
                self.assertIn((URIRef('urn:query'), RDFS.member, URIRef('urn:item')), graph)
                self.assertIn((URIRef('urn:item'), URIRef('urn:relation'), URIRef('urn:target')), graph)
                self.assertIn((URIRef('urn:item'), RDF.type, URIRef('urn:Class')), graph)

    def test_unacceptable_media_returns_406(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as raised:
            represent({'uri': 'urn:item'}, SimpleNamespace(headers={'accept': 'image/png'}))
        self.assertEqual(raised.exception.status_code, 406)

    def test_shape_uses_oslc_property_definition(self):
        response = represent({'uri': 'urn:shape', 'type': 'oslc:ResourceShape',
                              'properties': [{'uri': 'urn:property', 'name': 'size'}]},
                             SimpleNamespace(headers={'accept': 'text/turtle'}))
        graph = Graph().parse(data=response.body, format='turtle')
        shape_property = next(graph.objects(URIRef('urn:shape'), URIRef('http://open-services.net/ns/core#property')))
        self.assertIn((shape_property, URIRef('http://open-services.net/ns/core#propertyDefinition'), URIRef('urn:property')), graph)
