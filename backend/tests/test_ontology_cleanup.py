import ast
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.depo_platform.ontology_cleanup import clear_ontology_registrations


class CleanupTests(unittest.TestCase):
    def stores(self):
        upload = SimpleNamespace(clear_all_metadata=Mock(return_value={'status':'success','cleared':1}),
            _invalidate_list_cache=Mock(), list_all_ontologies=Mock(return_value={'status':'success','ontologies':[]}))
        catalog = SimpleNamespace(clear_registration_metadata=Mock(return_value={'status':'success','cleared':1}),
                                  list=Mock(return_value=[]))
        return upload, catalog

    def test_success_requires_empty_readback(self):
        result = clear_ontology_registrations(*self.stores())
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['verification']['catalog']['remaining'], 0)

    def test_surviving_registration_is_partial(self):
        upload, catalog = self.stores()
        catalog.list.return_value = [{'ontology_id':'old'}]
        result = clear_ontology_registrations(upload, catalog)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['verification']['catalog']['remaining'], 1)

    def test_failed_ingestion_cleanup_does_not_skip_catalog(self):
        upload, catalog = self.stores()
        upload.clear_all_metadata.side_effect = RuntimeError('unavailable')
        with self.assertLogs(level='ERROR'):
            result = clear_ontology_registrations(upload, catalog)
        catalog.clear_registration_metadata.assert_called_once()
        self.assertEqual(result['status'], 'partial')

    def test_failed_readback_is_not_empty(self):
        upload, catalog = self.stores()
        catalog.list.side_effect = RuntimeError('unavailable')
        with self.assertLogs(level='ERROR'):
            result = clear_ontology_registrations(upload, catalog)
        self.assertEqual(result['verification']['catalog'], {'status':'unverified','remaining':None})

    def test_index_failure_after_data_deletion_still_clears_registrations(self):
        tree = ast.parse(Path('backend/routes/admin_routes.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'clean_neo4j_schema')
        fn.decorator_list = []
        cleaner = SimpleNamespace(reset_database=lambda **kw: {'status':'FAIL','data_deleted':True,'message':'index failure'}, close=lambda:None)
        scope = dict(CleanSchemaRequest=object, CLEAN_SCHEMA_CONFIRM_TOKEN='confirm', SCHEMA_CLEANER_AVAILABLE=True,
            Neo4jSchemaCleaner=lambda:cleaner, _reconcile_reset=lambda:{'status':'success'}, logger=logging.getLogger(__name__),
            OSLCTRSService=SimpleNamespace(publish_event=lambda *a,**kw:None, base_resource_uri=lambda:'urn:test'))
        exec(compile(ast.Module(body=[fn],type_ignores=[]), '<cleanup>', 'exec'), scope)
        outcome={'status':'success','cleared':2,'failed':[], 'verification':{}}
        with patch.dict('sys.modules', {'backend.depo_platform.maintenance': SimpleNamespace(invalidate_shared_caches=lambda: True)}), patch('backend.depo_platform.import_cleanup.clear_import_workflows', return_value={'status':'success','deleted_count':0}), patch('backend.depo_platform.ontology_cleanup.clear_ontology_registrations', return_value=outcome) as clear:
            result = scope['clean_neo4j_schema'](SimpleNamespace(confirm='confirm'))
        clear.assert_called_once()
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['graph_cleanup_message'], 'index failure')
