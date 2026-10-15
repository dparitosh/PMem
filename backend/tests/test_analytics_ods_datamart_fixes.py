"""ODS correctness, exact field identities, data mart guards and batch mapping."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch

from backend.data_pipeline_service.xml_analytics import business_view_plan, materialize_xml
from backend.data_pipeline_service.analytics_fields import resolve_property
from backend.tests import test_xml_analytics_materialization as fixtures
HEADER = fixtures.HEADER


class AnalyticsFixes(unittest.TestCase):
    def prepare(self, *args, **kwargs):
        return fixtures.XMLAnalyticsMaterialization().prepare(*args, **kwargs)

    def test_polymorphic_xml_is_rejected_before_fields_can_be_lost(self):
        schema=HEADER+'<xs:complexType name="Base"><xs:sequence><xs:element name="name" type="xs:string"/></xs:sequence></xs:complexType><xs:complexType name="Derived"><xs:complexContent><xs:extension base="t:Base"><xs:attribute name="serial" type="xs:string" use="required"/></xs:extension></xs:complexContent></xs:complexType><xs:element name="Root" type="t:Base"/></xs:schema>'
        xml=b'<Root xmlns="urn:test" xmlns:t="urn:test" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="t:Derived" serial="KEEP-ME"><name>Pump</name></Root>'
        with self.assertRaisesRegex(ValueError,'polymorphic projection'):
            self.prepare(xml,schema)

    def test_attribute_and_element_same_name_require_exact_selection(self):
        schema=HEADER+'<xs:element name="Root"><xs:complexType><xs:sequence><xs:element name="value" type="xs:int"/></xs:sequence><xs:attribute name="value" type="xs:int"/></xs:complexType></xs:element></xs:schema>'
        prepared=self.prepare(b'<Root xmlns="urn:test" value="7"><value>12</value></Root>',schema)
        entity=prepared['model']['tables'][0]
        definition={'name':'By value','entity_id':entity['entity_id'],'grain':'entity-instance','group_by':['value'],'measures':[{'name':'rows','aggregate':'count'}]}
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            business_view_plan(prepared['model'],prepared['schema'],[definition])
        for column in entity['columns']:
            view=business_view_plan(prepared['model'],prepared['schema'],[{**definition,'group_by':[column['sql_name']]}])[0]
            self.assertIn('GROUP BY "'+column['sql_name']+'"',view['sql'])
            self.assertIs(resolve_property(entity,column['source_kind']+':'+column['source_qname']),column)

    def test_numeric_precision_aggregates_accept_decimal_types(self):
        model={'tables':[{'entity_id':'E','sql_name':'entity','columns':[{'name':'amount','sql_name':'amount_column','sql_type':'NUMERIC(10,2)'}]}]}
        for aggregate in ('sum','avg','min','max'):
            view=business_view_plan(model,'ods',[{'name':'Metric','entity_id':'E','grain':'entity-instance','measures':[{'name':'result','aggregate':aggregate,'property':'amount'}]}])[0]
            self.assertIn(aggregate.upper()+'("amount_column")',view['sql'])

    def test_opt_in_facets_validate_source_without_decimal_rounding(self):
        schema=HEADER+'<xs:element name="Root"><xs:simpleType><xs:restriction base="xs:decimal"><xs:totalDigits value="5"/><xs:fractionDigits value="2"/></xs:restriction></xs:simpleType></xs:element></xs:schema>'
        with self.assertRaisesRegex(ValueError,'facets'):
            self.prepare(b'<Root xmlns="urn:test">12345</Root>',schema)
        prepared=self.prepare(b'<Root xmlns="urn:test">12345</Root>',schema,{'constraint_policy':'validated-source'})
        self.assertEqual(prepared['rows'][0][1],['12345'])
        self.assertEqual(prepared['model']['tables'][0]['columns'][0]['sql_type'],'NUMERIC')
        with self.assertRaisesRegex(ValueError,'does not conform'):
            self.prepare(b'<Root xmlns="urn:test">123456</Root>',schema,{'constraint_policy':'validated-source'})

    def test_fixed_values_still_require_valid_xml(self):
        schema=HEADER+'<xs:element name="Root" type="xs:string" fixed="required"/></xs:schema>'
        result=self.prepare(b'<Root xmlns="urn:test">required</Root>',schema,{'constraint_policy':'validated-source'})
        self.assertEqual(result['rows'][0][1],['required'])
        empty=self.prepare(b'<Root xmlns="urn:test"/>',schema,{'constraint_policy':'validated-source'})
        self.assertEqual(empty['rows'][0][1],['required'])
        with self.assertRaisesRegex(ValueError,'does not conform'):
            self.prepare(b'<Root xmlns="urn:test">wrong</Root>',schema,{'constraint_policy':'validated-source'})

    def test_source_constraint_option_does_not_enable_unsupported_choices(self):
        schema=HEADER+'<xs:element name="Root"><xs:complexType><xs:choice><xs:element name="a" type="xs:string"/><xs:element name="b" type="xs:string"/></xs:choice></xs:complexType></xs:element></xs:schema>'
        with self.assertRaisesRegex(ValueError,'Choice'):
            self.prepare(b'<Root xmlns="urn:test"><a>x</a></Root>',schema,{'constraint_policy':'validated-source'})

    def dimension(self):
        model={'tables':[{'entity_id':'Part','sql_name':'parts','columns':[{'name':'key','sql_name':'part_key','sql_type':'TEXT'},{'name':'name','sql_name':'part_name','sql_type':'TEXT'}]}]}
        definition={'name':'Part dimension','kind':'dimension','entity_id':'Part','grain':'business-key','keys':['key'],'attributes':['name'],'history_policy':'immutable'}
        return model,definition

    def test_dimension_plan_uses_explicit_keys_and_rejects_ambiguous_history(self):
        model,definition=self.dimension()
        view=business_view_plan(model,'ods',[definition])[0]
        self.assertIn('SELECT DISTINCT "part_key","part_name"',view['sql'])
        self.assertIn('"part_key" IS NULL',view['validation_sql'])
        self.assertIn('COUNT(DISTINCT jsonb_build_array("part_name")) > 1',view['validation_sql'])
        for change in ({'keys':[]},{'history_policy':'guess'},{'attributes':['part_key']},{'keys':['missing']}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                business_view_plan(model,'ods',[{**definition,**change}])

    def database(self, invalid_dimension=False):
        class Database:
            def __init__(self):self.calls=[];self.end=None;self.next=100
            def __enter__(self):return self
            def __exit__(self,*args):pass
            @contextmanager
            def transaction(self):
                try:yield self
                except Exception:self.end='rollback';raise
                else:self.end='commit'
            def cursor(self):return self
            def execute(self,query,params=None):
                self.query=query.as_string() if hasattr(query,'as_string') else query
                self.params=params;self.calls.append((self.query,params))
            def fetchone(self):return (invalid_dimension,) if self.query.endswith(' AS invalid') else None
            def fetchall(self):
                count=self.params[1]+1;result=[(index,self.next+index) for index in range(count)];self.next+=count
                return list(reversed(result))
        return Database()

    def load(self, prepared, database):
        class Registry:
            namespace='xml_analytics_loads'
            def __init__(self,*args):pass
            def _connect(self):return database
        with patch('backend.data_pipeline_service.xml_analytics.prepare_xml_load',return_value=prepared),patch('backend.data_pipeline_service.xml_analytics.PostgresRegistry',Registry):
            return materialize_xml({},correlation_id='test')

    def test_large_load_batches_rows_and_links_and_maps_explicit_ordinals(self):
        schema=HEADER+'<xs:element name="Root"><xs:complexType><xs:sequence><xs:element name="tag" type="xs:string" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element></xs:schema>'
        prepared=self.prepare(('<Root xmlns="urn:test">'+''.join('<tag>'+str(i)+'</tag>' for i in range(1200))+'</Root>').encode(),schema)
        database=self.database();receipt=self.load(prepared,database)
        inserts=[(query,args) for query,args in database.calls if 'OVERRIDING SYSTEM VALUE' in query]
        self.assertEqual(len(inserts),4)
        self.assertEqual(receipt['counts']['entities'],1201)
        link_inserts=[args for query,args in database.calls if '(owner_id,child_id,position)' in query]
        self.assertEqual(len(link_inserts),3)
        self.assertEqual(link_inserts[0][:6],[100,101,0,100,102,1])
        self.assertEqual(database.end,'commit')

    def test_dimension_conflict_rolls_back_load_and_receipt(self):
        prepared=self.prepare(b'<Root xmlns="urn:test" id="7"><tag>A</tag></Root>')
        entity=prepared['model']['tables'][0]
        definition={'name':'ID dimension','kind':'dimension','entity_id':entity['entity_id'],'grain':'business-key','keys':[entity['columns'][0]['sql_name']],'attributes':[],'history_policy':'immutable'}
        prepared['business_views']=business_view_plan(prepared['model'],prepared['schema'],[definition])
        database=self.database(invalid_dimension=True)
        with self.assertRaisesRegex(ValueError,'Dimension keys'):
            self.load(prepared,database)
        self.assertEqual(database.end,'rollback')
        self.assertFalse(any('INSERT INTO depo_registry' in query and args[0]=='xml_analytics_loads' for query,args in database.calls))


if __name__=='__main__':unittest.main()
