import json,unittest,uuid,tempfile
from pathlib import Path
from backend.Services.import_identity import attach_plmxml_identities,stamp_instance_identity
from backend.Services.xsd_identity import class_iri_map
from backend.Services.xsd_semantics import expand_model_groups

class SourceIdentityTests(unittest.TestCase):
 def test_preserves_application_refs_and_source_identifiers_separately(self):
  rows=[{'id':'id1','import_row_key':'row1'}]
  attach_plmxml_identities(b'<PLMXML xmlns="urn:source"><Product id="id1" uid="source-uid" uuid="legacy-uuid"><ApplicationRef application="Teamcenter" label="opaque-identity" version="A"/></Product></PLMXML>',rows)
  row=rows[0];stamp_instance_identity(row,'task-a');first=row['uuid']
  self.assertEqual(row['source_uid'],'source-uid');self.assertEqual(row['source_uuid'],'legacy-uuid')
  self.assertEqual(json.loads(row['source_application_refs_json'])[0]['label'],'opaque-identity')
  self.assertEqual(row['source_element_namespace'],'urn:source');self.assertEqual(row['source_element_name'],'Product')
  self.assertEqual(str(uuid.UUID(first)),first);self.assertEqual(row['iri'],'urn:pmem:instance:'+first)
  stamp_instance_identity(row,'task-a');self.assertEqual(first,row['uuid'])
  stamp_instance_identity(row,'task-b');self.assertNotEqual(first,row['uuid'])
 def test_references_on_filtered_metadata_owners_remain_in_manifest(self):
  records=attach_plmxml_identities(b'<PLMXML><Product id="id1"><ApplicationRef label="business"/></Product><Metadata id="meta"><ApplicationRef label="metadata-identity"/></Metadata></PLMXML>',[{'id':'id1'}])
  self.assertEqual(len(records),2);self.assertFalse(records[1]['retained_instance'])
  self.assertEqual(records[1]['attributes']['label'],'metadata-identity')
 def test_no_fabricated_source_uid_or_uuid(self):
  rows=[{'id':'id1'}];attach_plmxml_identities(b'<PLMXML><Product id="id1"/></PLMXML>',rows)
  self.assertNotIn('source_uid',rows[0]);self.assertNotIn('source_uuid',rows[0])
  with self.assertRaises(ValueError):stamp_instance_identity(rows[0],'task')
 def test_source_namespaces_survive_qualified_collision_names(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   a=root/'a.xsd';b=root/'b.xsd'
   a.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a"><xs:complexType name="Base"/><xs:element name="Base" type="xs:string"/></xs:schema>')
   b.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:a="urn:a" targetNamespace="urn:b"><xs:import namespace="urn:a" schemaLocation="a.xsd"/><xs:complexType name="Base"><xs:complexContent><xs:extension base="a:Base"/></xs:complexContent></xs:complexType></xs:schema>')
   expanded=expand_model_groups([a,b]);mapping=class_iri_map(expanded)
   self.assertIn('urn:a#Base',mapping.values());self.assertIn('urn:b#Base',mapping.values());self.assertIn('urn:a#element/Base',mapping.values())
   self.assertEqual(len(set(mapping.values())),len(mapping))
   converted_child=next(n for n in expanded[b] if n.tag.endswith('complexType'))
   base=next(n for n in converted_child.iter() if n.tag.endswith('extension')).get('base')
   self.assertEqual(mapping[base],'urn:a#Base')
class ConvertedNamespaceTests(unittest.TestCase):
 def test_generated_subclass_edge_uses_both_source_namespaces(self):
  from rdflib import Graph,URIRef
  from rdflib.namespace import RDFS
  from backend.Services.owl_xsd_engine import OntologyConfig,convert_xsd_to_owl
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   (root/'a.xsd').write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a"><xs:complexType name="Parent"/></xs:schema>')
   (root/'b.xsd').write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:a="urn:a" targetNamespace="urn:b"><xs:import namespace="urn:a" schemaLocation="a.xsd"/><xs:complexType name="Child"><xs:complexContent><xs:extension base="a:Parent"/></xs:complexContent></xs:complexType></xs:schema>')
   out=root/'model.ttl'
   cfg=OntologyConfig(base_uri='urn:generated#',prefix='g',title='Test',description='Namespace regression',schema_dir=folder,output_ttl=str(out))
   convert_xsd_to_owl(cfg)
   graph=Graph().parse(out,format='turtle')
   self.assertIn((URIRef('urn:b#Child'),RDFS.subClassOf,URIRef('urn:a#Parent')),graph)
if __name__=='__main__':unittest.main()
