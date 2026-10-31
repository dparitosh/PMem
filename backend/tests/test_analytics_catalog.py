import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from backend.data_pipeline_service import analytics_catalog as catalog
from backend.data_pipeline_service.xml_analytics import business_view_plan

class AnalyticsCatalogTests(unittest.TestCase):
    def test_unknown_relation_rejected_before_database_access(self):
        with patch.object(catalog,'retained',return_value=({}, {'schema':'safe'}, {'tables':[]})), patch.object(catalog,'PostgresRegistry') as registry:
            with self.assertRaises(HTTPException) as raised:
                catalog.inspect('run', 'source_documents; DROP SCHEMA public')
            self.assertEqual(raised.exception.status_code,404)
            registry.assert_not_called()

    def test_missing_or_unverified_ownership_rejected(self):
        run={'run_id':'run','status':'completed','job_type':'xml-analytics-materialize','output_manifest':{'ods_receipt':{'status':'completed','schema':'safe','schema_digest':'one'}}}
        for owner in (None, {'schema_digest':'two','model':{}}, {'schema_digest':'one'}):
            with self.subTest(owner=owner),patch.object(catalog,'PostgresRegistry') as registry:
                registry.return_value.get.side_effect=[run,owner]
                with self.assertRaises(HTTPException) as raised:catalog.retained('run')
                self.assertEqual(raised.exception.status_code,409)

    def test_schema_identifier_is_not_sql(self):
        for schema in ('x;drop schema public',None):
            with patch.object(catalog,'PostgresRegistry') as registry:
                registry.return_value.get.return_value={'run_id':'r','status':'completed','job_type':'xml-analytics-materialize','output_manifest':{'ods_receipt':{'status':'completed','schema':schema}}}
                with self.assertRaises(HTTPException) as raised:catalog.retained('r')
                self.assertEqual(raised.exception.status_code,409)

    def test_preview_is_allowlisted_readonly_and_bounded(self):
        run={'run_id':'r'};receipt={'schema':'safe'};model={'tables':[{'sql_name':'parts','name':'Parts','entity_id':'Part'}]}
        cursor=MagicMock();cursor.fetchall.side_effect=[[('parts','name','text'),('parts','source_document_sha256','text')],[('Bearing',),('Motor',)]]
        db=MagicMock();db.cursor.return_value.__enter__.return_value=cursor
        with patch.object(catalog,'retained',return_value=(run,receipt,model)),patch.object(catalog,'PostgresRegistry') as registry:
            registry.return_value._connect.return_value.__enter__.return_value=db
            result=catalog.inspect('r','parts',1)
        self.assertTrue(result['read_only']);self.assertTrue(result['limited'])
        self.assertEqual(result['rows'],[['Bearing']]);self.assertEqual(result['columns'],[{'name':'name','type':'text'}])
        self.assertIn('READ ONLY',cursor.execute.call_args_list[0].args[0])
        self.assertEqual(cursor.execute.call_args_list[-1].args[1],(2,))

    def test_kpi_requires_explicit_business_definition(self):
        model={'tables':[{'entity_id':'part','sql_name':'parts','columns':[]}]}
        definition={'name':'Parts count','kind':'kpi','grain':'entity-instance','entity_id':'part','measures':[{'name':'parts','aggregate':'count'}]}
        with self.assertRaisesRegex(ValueError,'description and unit'):business_view_plan(model,'safe',[definition])
        plan=business_view_plan(model,'safe',[{**definition,'description':'Number of loaded parts','unit':'parts'}])[0]
        self.assertEqual(plan['kind'],'kpi');self.assertEqual(plan['unit'],'parts')
        self.assertIn('COUNT(*)',plan['sql'])
