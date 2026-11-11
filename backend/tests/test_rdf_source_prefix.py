import unittest
from unittest.mock import patch
from backend.ingestion_service.rdf_conversion import convert_rdf
class FakeStore:
 def ingest_bytes(self,*args,**kwargs):return {'artifact_id':'test-artifact'}
class RdfPrefixTests(unittest.TestCase):
 def test_prefix_comes_from_declared_namespace_for_turtle_and_xml(self):
  from rdflib import Graph
  turtle=b'@prefix owl:<http://www.w3.org/2002/07/owl#>. <http://www.plmxml.org/Schemas/PLMXMLSchema#> a owl:Ontology.'
  for filename,content in [('model.ttl',turtle),('model.rdf',Graph().parse(data=turtle,format='turtle').serialize(format='xml').encode())]:
   with self.subTest(filename=filename),patch('backend.ingestion_service.rdf_conversion.ArtifactStore',FakeStore):
    result=convert_rdf(filename=filename,content=content)['ontology']
    self.assertEqual(result['prefix'],'plmxmlschema');self.assertEqual(result['namespace_status'],'declared')
 def test_multiple_ontology_declarations_are_not_arbitrarily_selected(self):
  with patch('backend.ingestion_service.rdf_conversion.ArtifactStore',FakeStore):
   result=convert_rdf(filename='model.ttl',content=b'@prefix owl:<http://www.w3.org/2002/07/owl#>. <urn:a> a owl:Ontology. <urn:b> a owl:Ontology.')['ontology']
  self.assertEqual(result['namespace_status'],'missing_or_ambiguous');self.assertEqual(result['base_uri'],'')
if __name__=='__main__':unittest.main()
