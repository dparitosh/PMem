import tempfile
import unittest
from pathlib import Path
from backend.Services.xsd_relational_report import build_xsd_relational_report
from backend.Services.xsd_analytics_plan import build_analytics_schema_plan

PREFIX='<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:test" targetNamespace="urn:test">'
class XSDAnalytics(unittest.TestCase):
    def model(self, body):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'source.xsd';path.write_text(PREFIX+body+'</xs:schema>',encoding='utf-8')
            return build_xsd_relational_report(path)
    def test_anonymous_root_and_repeated_scalar_materialization(self):
        model=self.model('<xs:element name="Root"><xs:complexType><xs:sequence><xs:element name="tag" type="xs:string" minOccurs="0" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>')
        self.assertEqual(len(model['tables']),2)
        self.assertEqual(model['roots'][0]['source_qname'],'{urn:test}Root')
        self.assertEqual(model['tables'][0]['relationships'][0]['max_occurs'],'unbounded')
        plan=build_analytics_schema_plan(model)
        if model['validation']['formal_xsd_validation']=='compiled': self.assertIn('REFERENCES',plan['sql'])
        else: self.assertTrue(plan['ddl_blockers'])
        self.assertFalse(plan['ready_for_automatic_execution'])
    def test_choice_and_repeating_group_block_ddl(self):
        model=self.model('<xs:complexType name="Record"><xs:sequence><xs:choice><xs:element name="a" type="xs:string"/><xs:element name="b" type="xs:string"/></xs:choice><xs:sequence minOccurs="0" maxOccurs="unbounded"><xs:element name="tag" type="xs:string"/></xs:sequence></xs:sequence></xs:complexType>')
        self.assertFalse(model['columns'][0]['required'])
        self.assertEqual(model['tables'][0]['relationships'][0]['max_occurs'],'unbounded')
        self.assertEqual(build_analytics_schema_plan(model)['sql'],'')
    def test_datatype_facets_and_prohibited_attributes(self):
        model=self.model('<xs:simpleType name="Money"><xs:restriction base="xs:decimal"><xs:totalDigits value="12"/><xs:fractionDigits value="2"/></xs:restriction></xs:simpleType><xs:complexType name="Record"><xs:attribute name="hidden" type="xs:string" use="prohibited"/><xs:attribute name="cost" type="t:Money"/></xs:complexType>')
        self.assertEqual(len(model['columns']),1)
        self.assertEqual(model['columns'][0]['sql_type'],'NUMERIC(12,2)')
        self.assertIn('fractionDigits',model['columns'][0]['facets'])
    def test_bad_xml_missing_dependency_and_traversal_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'source.xsd'
            for text in ('<invalid',PREFIX+'<xs:include schemaLocation="missing.xsd"/></xs:schema>',PREFIX+'<xs:include schemaLocation="../outside.xsd"/></xs:schema>'):
                path.write_text(text)
                with self.assertRaises(ValueError): build_xsd_relational_report(path)
    def test_imported_same_name_types_remain_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'other.xsd').write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:other"><xs:complexType name="Record"><xs:attribute name="other" type="xs:string"/></xs:complexType></xs:schema>')
            (root/'source.xsd').write_text(PREFIX+'<xs:import namespace="urn:other" schemaLocation="other.xsd"/><xs:complexType name="Record"><xs:attribute name="local" type="xs:string"/></xs:complexType></xs:schema>')
            model=build_xsd_relational_report(root/'source.xsd')
            self.assertEqual({table['entity_id'] for table in model['tables']},{'{urn:test}Record','{urn:other}Record'})
            self.assertEqual(len({table['sql_name'] for table in model['tables']}),2)
    def test_nillable_required_element_allows_null_column(self):
        model=self.model('<xs:complexType name="Record"><xs:sequence><xs:element name="optionalValue" type="xs:string" nillable="true"/></xs:sequence></xs:complexType>')
        self.assertTrue(model['columns'][0]['required']);self.assertTrue(model['columns'][0]['nullable'])
        self.assertNotIn('TEXT NOT NULL',build_analytics_schema_plan(model)['sql'])
    def test_converter_retains_model_plan_and_v2_product_artifacts(self):
        import ast, json, threading
        from enum import Enum
        from typing import Any
        class FileType(Enum): XSD='xsd'; EXPRESS='exp'; STEP='step'; XMI='xmi'
        artifacts=[]
        class Store:
            def ingest_bytes(self,content,**metadata):
                result={'artifact_id':'artifact-'+str(len(artifacts)), **metadata, 'content':content}
                artifacts.append(result);return result
        tree=ast.parse(Path('backend/ingestion_service/schema_conversion.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EngineeringSchemaConverter')
        namespace={'Any':Any,'FileType':FileType,'FileFormatDetector':type('Detector',(),{'detect':staticmethod(lambda f:FileType.XSD)}),
            '_SOURCE_KINDS':{FileType.XSD:'schema'},'inspect_xsd_structure':lambda content:{'status':'structurally_valid'},
            '_XSD_CONVERSION_LOCK':threading.Lock(),'OWLGenerationService':type('OWL',(),{'generate_owl':staticmethod(lambda *a:('@prefix x: <urn:test:> .',{'classes':1}))}),
            'ArtifactStore':Store,'Path':Path,'tempfile':tempfile,'json':json,'build_xsd_relational_report':build_xsd_relational_report,'build_analytics_schema_plan':build_analytics_schema_plan}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual converter>','exec'),namespace)
        converter=namespace['EngineeringSchemaConverter']();converter._ap242_representation=lambda **kwargs:None
        result=converter.convert(filename='model.xsd',content=(PREFIX+'<xs:element name="Root" type="xs:string"/></xs:schema>').encode())
        self.assertEqual(result['data_product_draft']['contract'],'schema-analytics-data-product-v2')
        self.assertEqual(result['data_product_draft']['quality_status'],'requires_review')
        self.assertEqual(set(result['artifacts']),{'source','serialization','analytics_profile','structural_model','analytics_schema_plan'})
        self.assertEqual(len(result['data_product_draft']['artifacts']),5)
        profile=json.loads(next(a['content'] for a in artifacts if a['kind']=='schema-analytics-profile'))
        self.assertEqual(profile['structural_model']['roots'][0]['source_qname'],'{urn:test}Root')
        self.assertFalse(profile['analytics_schema_plan']['ready_for_automatic_execution'])

    def test_schema_analytics_job_accepts_v2_without_spark(self):
        import ast, json, time, uuid, sys
        from typing import Any
        from collections import deque
        from types import SimpleNamespace
        from unittest.mock import patch
        tree=ast.parse(Path('backend/data_pipeline_service/runner.py').read_text(encoding='utf-8'))
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and any(isinstance(m,ast.FunctionDef) and m.name=='build_schema_analytics_product' for m in n.body))
        fn=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name=='build_schema_analytics_product')
        converted={'data_product_draft':{'contract':'schema-analytics-data-product-v2','artifacts':['one'],'quality_status':'requires_review'},'statistics':{'classes':1},'structural_model':{'tables':[]},'analytics_schema_plan':{'execution_mode':'review-only'},'artifacts':{'analytics_profile':'one'}}
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'source.xsd';source.write_text(PREFIX+'</xs:schema>')
            store=type('Store',(),{'resolve':lambda self,id:({'filename':'model.xsd','kind':'engineering-schema-source'},source)})
            namespace={'Any':Any,'ArtifactStore':store,'Path':Path,'time':time,'json':json,'uuid':uuid}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual analytics job>', 'exec'),namespace)
            runner=SimpleNamespace(_runs=deque(),_now=lambda:'now',_spark_session=lambda:(_ for _ in ()).throw(AssertionError('Spark must not be needed')))
            with patch.dict(sys.modules,{'backend.ingestion_service.schema_conversion':SimpleNamespace(converter=SimpleNamespace(convert=lambda **kw:converted))}):
                result=namespace['build_schema_analytics_product'](runner,{'artifact_id':'one'},correlation_id='trace')
            self.assertEqual(result['analytics_schema_plan']['execution_mode'],'review-only')
            self.assertEqual(result['data_product_draft']['quality_status'],'requires_review')

if __name__=='__main__': unittest.main()
