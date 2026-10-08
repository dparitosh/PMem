import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.agentic_service.agent_usage import architecture
from backend.agentic_service.dt_bindings import extend_catalog
from backend.agentic_service.single_tool import definition, execute

class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.source = extend_catalog(json.loads(Path('backend/agentic_service/catalog.json').read_text()))

    def test_runtime_roles_and_permissions(self):
        summary = architecture(self.source)
        self.assertEqual((summary['agent_count'], summary['tool_count'], summary['workflow_count']), (26, 44, 4))
        self.assertEqual(len({a['id'] for a in summary['agents']}), 26)
        for agent in summary['agents']:
            self.assertTrue(agent['description'])
            for tool in agent['tools']:
                self.assertEqual(definition(self.source, 'single-tool:'+agent['id']+':'+tool)['steps'][0]['tool_id'], tool)

    def test_invalid_binding_cannot_gain_permissions(self):
        with self.assertRaises(ValueError): definition(self.source, 'single-tool:dt-self-learning-review:ontology.register')
        self.source['agents'][0]['tools'].append('missing')
        with self.assertRaises(ValueError): architecture(self.source)

    def test_queued_mutation_returns_workflow_handle(self):
        class HTTPException(Exception):
            def __init__(self, status_code, detail, headers=None): self.status_code=status_code
        async def enqueue(command, request):
            self.assertEqual(command['workflow_id'], 'single-tool:ontology-governor:ontology.register')
            return {'run_id': 'run-1', 'status': 'queued'}
        fake_routes = types.ModuleType('backend.agentic_service.router')
        fake_durable = types.ModuleType('backend.agentic_service.durable_workflows')
        fake_durable.execution_mode = lambda: 'worker'
        fake_durable.enqueue = enqueue
        fake_fastapi = types.ModuleType('fastapi'); fake_fastapi.HTTPException = HTTPException
        import backend.agentic_service as package
        with patch.dict(sys.modules, {'fastapi': fake_fastapi, 'backend.agentic_service.router': fake_routes, 'backend.agentic_service.durable_workflows': fake_durable}), patch.object(package, 'router', fake_routes, create=True):
            payload={'agent_id':'ontology-governor','tool_id':'ontology.register','wait_for_completion':False}
            result=asyncio.run(execute(payload, object()))
            self.assertEqual(result['execution_kind'], 'workflow')
            self.assertEqual(result['workflow_run_id'], 'run-1')
            with self.assertRaises(HTTPException) as failure:
                asyncio.run(execute({**payload,'wait_for_completion':'false'}, object()))
            self.assertEqual(failure.exception.status_code, 422)


    def test_http_rejection_does_not_open_transport_circuit(self):
        from backend.core.ollama_limits import _failure
        class HTTPError(OSError):
            __module__ = 'requests.exceptions'
            def __init__(self, code): self.response = types.SimpleNamespace(status_code=code)
        state={'active':0, 'failures':0, 'until':0, 'generation':0}
        for code in (400,401,403,404): _failure(state, 2, 30, HTTPError(code), state['generation'])
        self.assertEqual(state['failures'], 0)
        for code in (429,503): _failure(state, 2, 30, HTTPError(code), state['generation'])
        self.assertEqual(state['failures'], 2)
        self.assertGreater(state['until'], 0)

if __name__ == '__main__': unittest.main()
