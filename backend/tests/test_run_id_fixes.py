import ast
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from uuid import uuid4
from backend.agentic_service.workflow_control import checkpoint, WorkflowCancelled

class HTTPException(Exception):
    def __init__(self, status_code, detail, headers=None):
        self.status_code, self.detail, self.headers = status_code, detail, headers

class RunIds(unittest.TestCase):
    def namespace(self):
        self.observations = []
        self.records = []
        def start(**kw):
            record = {'run_id': 'agent-one', **kw}
            self.observations.append(record)
            return record, time.perf_counter()
        return {'Any': object, 'Request': object, '_agent_io': lambda fn, *a, **kw: asyncio.to_thread(fn, *a, **kw), 'sessions': SimpleNamespace(owner=lambda *a: 'owner'), 'asyncio': asyncio, 'time': time, 'os': __import__('os'), 'datetime': datetime, 'timezone': timezone, 'timedelta': timedelta, 'uuid4': uuid4,
            'plan': lambda value: {'requires_approval': False}, 'workflow_plan': lambda value: {'steps': []}, 'graph_read_identity': lambda request: None,
            'telemetry': SimpleNamespace(start=start), '_tool_span': lambda *a, **kw: None, '_finish_observation': lambda *a, **kw: None,
            '_now': lambda: datetime.now(timezone.utc).isoformat(), 'HTTPException': HTTPException,
            'catalog': SimpleNamespace(item=lambda *a: {'id': 'workflow', 'steps': []}), 'workflow_store': SimpleNamespace(put=lambda key, record: self.records.append(dict(record))),
            'logger': SimpleNamespace(exception=lambda *a: None)}
    def load(self, name, namespace):
        namespace.setdefault("workflow_checkpoint", checkpoint)
        namespace.setdefault("WorkflowCancelled", WorkflowCancelled)
        namespace.setdefault("workflow_controls", SimpleNamespace(get=lambda key: None))
        tree = ast.parse(Path('backend/agentic_service/router.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
        node.decorator_list = []
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual agent route>', 'exec'), namespace)
        return namespace[name]
    def test_tool_id_returned_and_exposed_on_error(self):
        namespace = self.namespace()
        async def dispatch(*args): return {'tool_id': 'tool', 'result': {}}
        namespace['_dispatch'] = dispatch
        request = SimpleNamespace(state=SimpleNamespace(request_id='request'))
        result = asyncio.run(self.load('run', namespace)({}, request))
        self.assertEqual(result['run_id'], 'agent-one')
        async def fail(*args): raise HTTPException(403, 'Denied')
        namespace['_dispatch'] = fail
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(namespace['run']({}, request))
        self.assertEqual(caught.exception.headers['X-DEPO-Run-ID'], 'agent-one')
    def test_workflow_and_telemetry_link_both_directions(self):
        namespace = self.namespace()
        result = asyncio.run(self.load('run_workflow', namespace)({'workflow_id': 'workflow'}, SimpleNamespace(state=SimpleNamespace(request_id='request'))))
        self.assertEqual(result['telemetry_run_id'], 'agent-one')
        self.assertEqual(self.observations[0]['workflow_run_id'], result['run_id'])

if __name__ == '__main__': unittest.main()
