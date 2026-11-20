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


class GoldenIdentityRegressionTests(unittest.TestCase):
 def test_normalization_preserves_identifiers_but_normalizes_measurements(self):
  from backend.ceim.normalization import normalize_record
  record, _ = normalize_record({'source_id':'000001', 'attributes':{
      'part_number':'000886', 'productId':'000886', 'serialNumber':'0012',
      'revision':'01', 'operationNumber':'0010', 'quantity':'0002.00'}})
  self.assertEqual(record['source_id'], '000001')
  for field,value in {'part_number':'000886','productId':'000886','serialNumber':'0012','revision':'01','operationNumber':'0010'}.items():
   self.assertEqual(record['attributes'][field], value)
  self.assertEqual(record['attributes']['quantity'], '2')

 def test_plmxml_product_number_and_revision_master_are_distinct(self):
  from backend.Services.plmxml_parser import parse_plmxml_file
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'parts.xml'
   path.write_text('<PLMXML><Product id="master" productId="000886" name="Shaft"/><ProductRevision id="revision" masterRef="#master" revision="A" name="Shaft"/></PLMXML>')
   doc=parse_plmxml_file(path)
   self.assertEqual(doc.parts['master'].part_number, '000886')
   self.assertEqual(doc.parts['revision'].master_ref, '#master')
   self.assertEqual(doc.parts['revision'].revision, 'A')

 def test_duplicate_plmxml_ids_and_ambiguous_uid_are_rejected(self):
  from backend.Services.plmxml_parser import parse_plmxml_file
  for content in ('<PLMXML><Product id="x"/><Product id="x"/></PLMXML>',
                  '<PLMXML><Product id="x" uid="same"/><Product id="y" uid="same"/></PLMXML>'):
   with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'invalid.xml';path.write_text(content)
    with self.assertRaises(ValueError):parse_plmxml_file(path)

 def test_canonical_scoping_rejects_duplicate_identity(self):
  from backend.ceim.identity import scope_batch
  with self.assertRaisesRegex(ValueError,'Duplicate'):
   scope_batch([{'id':'plmxml:1'},{'id':'plmxml:1'}],[],source_system='PLM')

 def test_oslc_iri_survives_database_node_recreation(self):
  from backend.oslc_service.identity import resource_uri
  properties={'iri':'urn:part:000886','ontology_id':'baseline-A'}
  self.assertEqual(resource_uri('https://nexus',properties,'old'),resource_uri('https://nexus',properties,'new'))
  self.assertIn('ontology_id=baseline-A',resource_uri('https://nexus',properties,'new'))


class RealMotorGoldenIdentityTests(unittest.TestCase):
 def test_motor_product_number_and_master_reference_match_source(self):
  from backend.Services.plmxml_parser import parse_plmxml_file
  source=Path('D:/GenAI_Projects/SPLM_Folder/plmxml_individual/000740_A_2-mBOM_INDUTION_MOTOR_ASSEMBLY 1.xml')
  if not source.is_file():self.skipTest('SPLM acceptance fixture not installed')
  doc=parse_plmxml_file(source)
  self.assertEqual(doc.parts['id1224'].part_number, '000886')
  self.assertEqual(doc.parts['id1222'].master_ref, '#id1224')
  self.assertEqual(doc.parts['id1222'].revision, 'A')


class ExternalIdentityReferenceTests(unittest.TestCase):
 def test_external_document_reference_is_not_rewritten_to_local_object(self):
  from backend.Services.plmxml_parser import _normalize_ref, _is_external_locator_ref
  self.assertEqual(_normalize_ref('#id123'), 'id123')
  self.assertEqual(_normalize_ref('other/id123.plmxml'), 'other/id123.plmxml')
  self.assertTrue(_is_external_locator_ref('locationRef', '000684_B.prt'))
  self.assertTrue(_is_external_locator_ref('locationRef', 'qafmetadata.qaf'))
