import ast
import logging
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

class HttpError(Exception):
    def __init__(self, status_code, detail): self.status_code,self.detail=status_code,detail


def actual(path,name,scope):
    tree=ast.parse(Path(path).read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    node.decorator_list=[]
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual integration>', 'exec'),scope)
    return scope[name]

class IntegrationFixes(unittest.TestCase):
    def test_retained_import_turtle_exports_without_generation_or_publication(self):
        module=ModuleType('fastapi.responses')
        module.Response=lambda **kwargs:kwargs
        fn=actual('backend/ingestion_service/tracked_import.py','export_ontology',
            dict(_status=lambda task:{'owl_ttl':'@prefix : <urn:> . :a :b :c .','filename':'part.xsd'},
                 MAX_UPLOAD_BYTES=1000,HTTPException=HttpError))
        with patch.dict(sys.modules,{'fastapi.responses':module}):
            result=fn('task-1','ttl')
            self.assertEqual(result['media_type'],'text/turtle')
            self.assertIn('part.xsd.ttl',result['headers']['Content-Disposition'])
            with self.assertRaises(HttpError) as error:fn('task-1','invalid')
            self.assertEqual(error.exception.status_code,422)

    def test_download_filename_header_is_exposed_by_shared_cors(self):
        tree=ast.parse(Path('backend/depo_platform/service_runtime.py').read_text(encoding='utf-8'))
        values=[ast.literal_eval(k.value) for n in ast.walk(tree) if isinstance(n,ast.Call)
                for k in n.keywords if k.arg=='expose_headers']
        self.assertTrue(values)
        self.assertTrue(all('Content-Disposition' in value for value in values))

    def test_graph_errors_do_not_expose_private_exception_details(self):
        def fail(**kwargs):raise RuntimeError('private-host-and-query')
        fn=actual('backend/graph_service/router.py','search',dict(
            publisher=SimpleNamespace(search=fail),HTTPException=HttpError,logger=logging.getLogger('audit')))
        with self.assertLogs('audit',level='ERROR') as logs:
            with self.assertRaises(HttpError) as error:fn('term')
        self.assertEqual(error.exception.status_code,503)
        self.assertNotIn('private-host-and-query',error.exception.detail)
        self.assertIn('private-host-and-query',' '.join(logs.output))
