import ast
import json
import os
import tempfile
import unittest
import uuid
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
from urllib.parse import quote, urlparse
from unittest.mock import patch
from types import SimpleNamespace
from backend.Services.oslc_query_service import OSLCQueryService
from backend.oslc_service.media import negotiate
from backend.mesh_store import PostgresRegistry

def load_sync():
    tree = ast.parse(Path('backend/oslc_service/sync.py').read_text(encoding='utf-8'))
    tree.body = [n for n in tree.body if not isinstance(n, ast.ImportFrom) or n.module != 'client']
    namespace = {'OSLCClient': object}
    exec(compile(tree, '<actual sync>', 'exec'), namespace)
    return namespace

class OSLCAudit(unittest.TestCase):
    def test_sync_collects_pages_and_rejects_cycles(self):
        namespace = load_sync()
        with tempfile.TemporaryDirectory() as temporary:
            store = namespace['OSLCSyncStore'](); store.root = Path(temporary)
            client = SimpleNamespace(base_url='https://provider.test/api', query=lambda *args: {'members': [{'uri': 'urn:one'}], 'nextPage': 'page2', 'oslc:totalCount': 2},
                                     next_page=lambda link, current_url: {'members': [{'uri': 'urn:two'}], 'oslc:totalCount': 2})
            sync = namespace['OSLCSynchronizer'](client, store)
            snapshot = sync.pull('resources', {})
            self.assertTrue(snapshot['complete'])
            self.assertEqual(snapshot['resource_count'], 2)
            client.next_page = lambda link, current_url: {'members': [], 'nextPage': 'page2'}
            with self.assertRaises(ValueError):
                sync.pull('resources', {})
            self.assertEqual(len(store.list()), 1)

    def test_quoted_operators_and_numeric_identity(self):
        conditions = OSLCQueryService.parse({'oslc.where': 'title="a>=b" and id="001"'}).where
        self.assertEqual([c.value for c in conditions], ['a>=b', '001'])
        self.assertEqual(OSLCQueryService.parse({'oslc.where': 'count>=12'}).where[0].value, 12)

    def test_negotiation_quality_parameters_and_exclusion(self):
        self.assertEqual(negotiate('text/turtle; charset=utf-8, application/json;q=0.5'), 'text/turtle')
        self.assertEqual(negotiate('application/json;q=0, */*;q=0.8'), 'text/turtle')
        self.assertIsNone(negotiate('application/json;q=0, text/turtle;q=0'))

    def test_members_partial_and_credential_redaction(self):
        namespace = load_sync()
        with tempfile.TemporaryDirectory() as temporary:
            store = namespace['OSLCSyncStore'](); store.root = Path(temporary)
            snapshot = store.create(resource_type='resources', parameters={'approval_token': 'synthetic', 'oslc.where': 'id="001"'}, payload={'members': [{'uri': 'urn:one'}], 'oslc:totalCount': 2})
            self.assertEqual(snapshot['resource_count'], 1)
            self.assertFalse(snapshot['complete'])
            self.assertNotIn('approval_token', store.get(snapshot['sync_id'])['parameters'])
            path = store._path(snapshot['sync_id'])
            value = json.loads(path.read_text()); value['parameters']['approval_token'] = 'synthetic'; path.write_text(json.dumps(value))
            namespace['redact_legacy_snapshots'](store)
            self.assertNotIn('synthetic', path.read_text())
            with self.assertRaises(ValueError): store.create(resource_type='resources', parameters={}, payload={'members': 'invalid'})

    def test_trs_deletion_and_stable_complete_paging(self):
        tree = ast.parse(Path('backend/Services/oslc_trs_service.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'OSLCTRSService')
        namespace = dict(PostgresRegistry=PostgresRegistry, threading=threading, datetime=datetime, timezone=timezone, timedelta=timedelta, uuid=uuid, os=os, json=json, Path=Path, quote=quote, urlparse=urlparse, Any=Any, Dict=Dict, List=List, Optional=Optional, contextmanager=contextmanager, time=time)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual TRS>', 'exec'), namespace)
        service = namespace['OSLCTRSService']
        rows = [{'element_id': str(i), 'title': str(i), 'labels': [], 'domain_properties': {}} for i in range(5)]
        graph = SimpleNamespace(GraphViewService=SimpleNamespace(_run=lambda *a: rows))
        oslc = SimpleNamespace(OSLCService=SimpleNamespace(resource_domain_types=lambda *a: []))
        ontology = SimpleNamespace(OntologyUploadManager=SimpleNamespace(list_ontologies=lambda: {'status': 'success', 'ontologies': []}))
        import sys
        with tempfile.TemporaryDirectory() as temporary, patch.dict(sys.modules, {'backend.Services.graph_view_service': graph, 'backend.Services.oslc_service': oslc, 'backend.Services.ontology_upload_manager': ontology}):
            path = Path(temporary) / 'change_log.json'
            service._storage_path = classmethod(lambda cls: path)
            service._storage_backend = classmethod(lambda cls: 'file')
            service.base_url = classmethod(lambda cls: 'http://oslc')
            service._load = classmethod(lambda cls: {'counter': 2, 'events': [{'resource_uri': '/oslc/resources/0', 'event_type': 'Creation'}, {'resource_uri': '/oslc/resources/0', 'event_type': 'Deletion'}]})
            first = service.base_resources(limit=2)
            self.assertEqual(first['total_count'], 4)
            self.assertNotIn('http://oslc/oslc/resources/0', [m['resource_uri'] for m in first['members']])
            rows.clear()
            second = service.base_resources(limit=2, snapshot_id=first['snapshot_id'], offset=2)
            self.assertEqual(second['count'], 2)
            self.assertIsNone(second['nextPage'])
            self.assertEqual(second['cutoff_order'], first['cutoff_order'])

    def test_graph_data_routes_have_auth_and_are_threadpool_handlers(self):
        tree = ast.parse(Path('backend/routes/oslc_routes.py').read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {'query_resources','get_resource','get_trs_base','get_trs_changelog','get_oslc_dictionary','get_oslc_taxonomy'}:
                self.assertIsInstance(node, ast.FunctionDef)
                self.assertIn('Depends(graph_read_identity)', ast.unparse(node.decorator_list[0]))

    def test_next_query_page_preserves_unicode_and_quoted_filters(self):
        from urllib.parse import urlencode, urlsplit, parse_qs
        tree = ast.parse(Path('backend/Services/oslc_service.py').read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OSLCService')
        fn = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_next_query_page')
        fn.decorator_list = []
        namespace = {'quote': quote, 'urlencode': urlencode}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<actual query continuation>', 'exec'), namespace)
        params = OSLCQueryService.parse({'oslc.where': 'title="工程>=001"', 'oslc.pageSize': 1})
        url = namespace['_next_query_page'](None, 'http://oslc', 'resources', params, 2)
        raw = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
        continued = OSLCQueryService.parse(raw)
        self.assertEqual(continued.where[0].value, params.where[0].value)
        self.assertEqual(continued.page_num, 2)

if __name__ == '__main__': unittest.main()
