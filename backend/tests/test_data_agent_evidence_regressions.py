import ast
import unittest
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def load(path, name, namespace, class_name=None):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    nodes = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name).body if class_name else tree.body
    node = next(n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), namespace)
    return namespace[name]


class DataAgentRegressions(unittest.TestCase):
    def runner(self):
        path = 'backend/data_pipeline_service/runner.py'
        namespace = dict(Any=Any, time=time, uuid=uuid)
        validate = load(path, '_validate_records', namespace, 'SparkJobRunner')
        assess = load(path, 'assess_data_quality', namespace, 'SparkJobRunner')
        retained = []
        class Frame:
            def groupBy(self, *args): return self
            def count(self): return self
            def orderBy(self, *args): return self
            def collect(self): return []
        def retain(records, **kwargs):
            retained.append((records, kwargs['kind']))
            return str(len(retained))
        runner = SimpleNamespace(max_records=100, _validate_records=validate,
            _lock=threading.Lock(), _spark_session=lambda: SimpleNamespace(createDataFrame=lambda records: Frame()),
            _retain_json_artifact=retain, _now=lambda: 'now', _runs=deque())
        return lambda records: assess(runner, {'records': records}, correlation_id='test'), retained

    def test_accepted_evidence_keeps_identity_provenance_and_source_fields(self):
        assess, retained = self.runner()
        record = dict(source_id='a', artifact_id='artifact', provenance={'system':'PLM'}, source_standard='QIF', canonical_concept='Part', custom='kept')
        result = assess([record])
        self.assertEqual(retained[0][0][0]['provenance'], record['provenance'])
        self.assertEqual(retained[0][0][0]['source_id'], 'a')
        self.assertEqual(retained[0][0][0]['custom'], 'kept')
        self.assertEqual(result['quality']['quality_gate'], 'passed')

    def test_all_rejected_retains_report_without_spark(self):
        assess, retained = self.runner()
        result = assess([{}])
        self.assertEqual(result['quality']['quality_gate'], 'failed')
        self.assertEqual(result['quality']['rejected_records'], 1)
        self.assertEqual(result['quality']['completeness'], 0)
        self.assertEqual(result['quality']['provenance'], 0)
        self.assertEqual(result['quality']['validity'], 0)
        self.assertIsNone(result['quality']['uniqueness'])
        self.assertEqual(result['quality']['dimension_not_assessed_records']['uniqueness'], 1)
        self.assertEqual(retained[1][1], 'rejected-data-quality-partition')
        self.assertEqual(len(retained[1][0]), 3)

    def test_duplicates_detected_even_when_first_record_lacks_provenance(self):
        assess, _ = self.runner()
        result = assess([dict(source_id='a',source_standard='QIF',canonical_concept='Part'), dict(source_id='a',artifact_id='artifact',source_standard='QIF',canonical_concept='Part')])
        self.assertEqual(result['quality']['uniqueness'], .5)
        self.assertEqual(result['quality']['rejected_records'], 2)

    def test_public_product_hides_internal_paths_and_credentials(self):
        public = load('backend/data_product_service/router.py', '_public_product', {})
        record = {'product_id':'a','status':'published','package_storage':{'zip_path':'private'},'api_key':'secret'}
        self.assertEqual(public(record), {'product_id':'a','status':'published'})
        self.assertIn('package_storage', record)

    def test_agent_dispatch_keeps_http_status(self):
        source = Path('backend/agentic_service/router.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        dispatch = next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_dispatch')
        handler = next(n for n in ast.walk(dispatch) if isinstance(n,ast.ExceptHandler) and isinstance(n.type,ast.Attribute) and n.type.attr=='HTTPStatusError')
        class HTTPException(Exception):
            def __init__(self,status_code,detail): self.status_code=status_code
        for status in (401,403,409,422,429,500,503):
            error = RuntimeError('downstream failure')
            error.response = SimpleNamespace(status_code=status)
            ns = {'HTTPException':HTTPException,'exc':error}
            with self.assertRaises(HTTPException) as caught:
                exec(compile(ast.Module(body=handler.body,type_ignores=[]),'<status handling>','exec'),ns)
            self.assertEqual(caught.exception.status_code,status)

if __name__ == '__main__': unittest.main()
