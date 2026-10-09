import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager
from lxml import etree

from backend.data_pipeline_service.xml_analytics import prepare_xml_load, flatten_xml, business_view_plan, materialize_xml
from backend.Services.xsd_relational_report import build_xsd_relational_report

HEADER = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:test" xmlns:t="urn:test" elementFormDefault="qualified">'
SCHEMA = HEADER + '<xs:element name="Root"><xs:complexType><xs:sequence><xs:element name="tag" type="xs:string" minOccurs="1" maxOccurs="3"/></xs:sequence><xs:attribute name="id" type="xs:int" use="required"/></xs:complexType></xs:element></xs:schema>'


class XMLAnalyticsMaterialization(unittest.TestCase):
    def prepare(self, content, schema=SCHEMA):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'source.xsd').write_text(schema)
            (root/'source.xml').write_bytes(content)
            class Store:
                def resolve(self, reference):
                    return ({'filename': 'source.xsd' if reference == 'schema' else 'source.xml', 'kind': 'engineering-schema-source'}, root / ('source.xsd' if reference == 'schema' else 'source.xml'))
            return prepare_xml_load({'schema_artifact_id': 'schema', 'xml_artifact_id': 'xml'}, Store())

    def test_unqualified_schema_loads_valid_instance(self):
        schema='<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="Root" type="xs:string"/></xs:schema>'
        result=self.prepare(b'<Root>value</Root>', schema)
        self.assertEqual(result['rows'][0][1], ['value'])

    def test_defaults_preserve_absence_nil_and_explicit_values(self):
        schema=HEADER+'<xs:element name="Root"><xs:complexType><xs:sequence><xs:element name="value" type="xs:string" default="fallback" minOccurs="0" nillable="true"/></xs:sequence></xs:complexType></xs:element></xs:schema>'
        for child, expected in [('<value/>', 'fallback'), ('', None), ('<value>explicit</value>', 'explicit'), ('<value xsi:nil="true"/>', None)]:
            with self.subTest(child=child):
                result=self.prepare(('<Root xmlns="urn:test" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'+child+'</Root>').encode(), schema)
                self.assertEqual(result['rows'][0][1], [expected])
        scalar=HEADER+'<xs:element name="Root" type="xs:string" default="root-default"/></xs:schema>'
        self.assertEqual(self.prepare(b'<Root xmlns="urn:test"/>',scalar)['rows'][0][1], ['root-default'])

    def test_nillable_complex_root_fails_closed(self):
        for value in ('true', '1'):
            schema=HEADER+'<xs:element name="Root" nillable="'+value+'"><xs:complexType><xs:sequence><xs:element name="value" type="xs:string"/></xs:sequence></xs:complexType></xs:element></xs:schema>'
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Nillable complex'):
                self.prepare(b'<Root xmlns="urn:test" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:nil="true"/>',schema)

    def test_validated_namespace_and_repeated_scalar_rows(self):
        original = b'<Root xmlns="urn:test" id="7"><tag>A</tag><tag>B</tag></Root>'
        result = self.prepare(original)
        self.assertEqual(result['original_bytes'], original)
        self.assertEqual(len(result['rows']), 3)
        self.assertEqual(len(result['links']), 2)
        self.assertEqual([link[-1] for link in result['links']], [0, 1])
        self.assertEqual(result['rows'][0][1], ['7'])
        self.assertEqual(result['rows'][1][1], ['A'])
        self.assertTrue(result['plan']['sql'])

    def test_invalid_xml_rejected_before_database_work(self):
        for xml in (b'<Root xmlns="urn:test" id="7"/>', b'<Root xmlns="urn:test" id="bad"><tag>A</tag></Root>', b'<!DOCTYPE x [<!ENTITY e "bad">]><Root/>'):
            with self.subTest(xml=xml), self.assertRaises(ValueError): self.prepare(xml)

    def test_namespace_ambiguity_does_not_match_local_name(self):
        with self.assertRaises(ValueError): self.prepare(b'<Root xmlns="urn:test" id="7"><tag xmlns="urn:other">A</tag></Root>')

    def test_profile_keeps_document_and_qualified_names(self):
        from backend.ingestion_service.profiles import SourceProfileStore
        store=SourceProfileStore.__new__(SourceProfileStore)
        profile={'profile_id':'test','version':1,'mapping':{'namespace_mode':'qualified','identifier':'id',
            'properties':{'{urn:a}name':'left','{urn:b}name':'right'}}}
        xml=b'<Root id="r"><a:name xmlns:a="urn:a">A</a:name><b:name xmlns:b="urn:b">B</b:name></Root>'
        result=store.normalize_batch(profile=profile,filename='instance.xml',content=xml)
        self.assertEqual(result['records_processed'],1)
        self.assertEqual(result['entities'][0]['left'],'A')
        self.assertEqual(result['entities'][0]['right'],'B')
        self.assertEqual(result['source_documents'][0]['tag'],'Root')
        self.assertEqual(len(result['source_documents'][0]['children']),2)
        with self.assertRaisesRegex(ValueError,'Ambiguous XML'):
            store.extract_records(profile={'mapping':{}},filename='instance.xml',content=xml)

    def test_decimal_total_digits_does_not_imply_zero_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.xsd'
            path.write_text(HEADER+'<xs:simpleType name="Money"><xs:restriction base="xs:decimal"><xs:totalDigits value="5"/></xs:restriction></xs:simpleType><xs:element name="amount" type="t:Money"/></xs:schema>')
            model=build_xsd_relational_report(path)
            self.assertEqual(model['columns'][0]['sql_type'], 'NUMERIC')
            self.assertTrue(model['ddl_blockers'])

    def test_business_metrics_require_explicit_entity_grain(self):
        prepared=self.prepare(b'<Root xmlns="urn:test" id="7"><tag>A</tag></Root>')
        entity=prepared['model']['roots'][0]['entity_id']
        view={'name':'Root count','entity_id':entity,'grain':'entity-instance','measures':[{'name':'count','aggregate':'count'}]}
        statements=business_view_plan(prepared['model'],prepared['schema'],[view])
        self.assertIn('COUNT(*)',statements[0]['sql'])
        with self.assertRaises(ValueError): business_view_plan(prepared['model'],prepared['schema'],[{**view,'grain':'unknown'}])
        with self.assertRaises(ValueError): business_view_plan(prepared['model'],prepared['schema'],[{**view,'measures':[{'name':'bad','aggregate':'execute'}]}])

    def test_load_stores_original_xml_and_rows_in_one_transaction(self):
        prepared=self.prepare(b'<Root xmlns="urn:test" id="7"><tag>A</tag></Root>')
        observed=[]
        class Database:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            @contextmanager
            def transaction(self):
                observed.append(('begin',None))
                try: yield
                except Exception:
                    observed.append(('rollback',None)); raise
                else: observed.append(('commit',None))
            def cursor(self): return self
            def execute(self,query,args=None):
                self.query=query.as_string() if hasattr(query,'as_string') else query
                observed.append((self.query,args))
            def fetchone(self):
                return (len(observed),) if 'RETURNING instance_id' in self.query else None
        database=Database()
        class Registry:
            namespace='xml_analytics_loads'
            def __init__(self,*args): pass
            def _connect(self): return database
        with patch('backend.data_pipeline_service.xml_analytics.prepare_xml_load',return_value=prepared), patch('backend.data_pipeline_service.xml_analytics.PostgresRegistry',Registry):
            receipt=materialize_xml({},correlation_id='trace')
        source_insert=next(args for query,args in observed if 'XMLPARSE(DOCUMENT' in query)
        self.assertEqual(source_insert[1],prepared['original_bytes'])
        self.assertEqual(receipt['counts']['entities'],2)
        self.assertEqual(observed[-1][0],'commit')
        self.assertTrue(any('source_document_sha256' in query for query,args in observed))
        observed.clear()
        with patch('backend.data_pipeline_service.xml_analytics.prepare_xml_load',return_value=prepared), patch('backend.data_pipeline_service.xml_analytics.PostgresRegistry',Registry), patch('backend.data_pipeline_service.xml_analytics.ensure_execution_allowed',side_effect=[None,RuntimeError('Lease lost')]):
            with self.assertRaisesRegex(RuntimeError,'Lease lost'): materialize_xml({},correlation_id='trace')
        self.assertEqual(observed[-1][0],'rollback')

    def test_identical_load_returns_receipt_without_inserting_rows(self):
        prepared=self.prepare(b'<Root xmlns="urn:test" id="7"><tag>A</tag></Root>')
        receipt={'status':'completed','counts':{'entities':2}}
        class Database:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def transaction(self): return self
            def cursor(self): return self
            def execute(self,query,args=None):
                self.query=query
                if 'INSERT' in query: raise AssertionError('Idempotent replay must not insert')
            def fetchone(self): return (receipt,)
        class Registry:
            namespace='xml_analytics_loads'
            def __init__(self,*args): pass
            def _connect(self): return Database()
        with patch('backend.data_pipeline_service.xml_analytics.prepare_xml_load',return_value=prepared), patch('backend.data_pipeline_service.xml_analytics.PostgresRegistry',Registry):
            self.assertEqual(materialize_xml({},correlation_id='retry'),receipt)


if __name__ == '__main__': unittest.main()
