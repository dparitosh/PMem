import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import tempfile


class StandaloneContractTests(unittest.TestCase):
    def test_aggregate_only_route_cannot_make_standalone_contract_pass(self):
        spec=importlib.util.spec_from_file_location('contract_audit',Path('scripts/frontend_api_contract.py'))
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config="""const CHAT_ENDPOINTS = {
  chat: setting('API_CHAT') || '/aggregate-only',
};
const SERVICE_PATHS = [
  ['ontology', /^\\/aggregate-only$/],
];
export const API = {
  chat: CHAT_ENDPOINTS,
};"""
        module.CONFIG_PATH=SimpleNamespace(read_text=lambda **_: config)
        module.SERVICE_MANIFEST_PATH=SimpleNamespace(read_text=lambda **_: '{"services":[{"id":"ontology","module":"backend.ontology_service.app:app"}]}')
        def load(name):
            paths={'/aggregate-only':{}} if name=='backend.main' else {'/standalone':{}}
            return SimpleNamespace(app=SimpleNamespace(openapi=lambda:{'paths':paths}))
        with tempfile.TemporaryDirectory() as directory:
            module.ROOT=Path(directory); module.CLIENT_ROOT=Path(directory)
            (Path(directory)/'client.js').write_text('apiClient.post(buildUrl(API.chat.chat), {});')
            with patch.object(module.importlib,'import_module',side_effect=load):
                report=module.classify_contract()
        self.assertEqual(report['status'],'fail')
        self.assertEqual(report['unclassified'][0]['path'],'/aggregate-only')

    def test_method_and_destination_are_both_required(self):
        spec=importlib.util.spec_from_file_location('contract_audit',Path('scripts/frontend_api_contract.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        config="""const SERVICE_PATHS = [
  ['ontology', /^\\/api\\/v1\\/ontologies(?:\\/|$)/],
];"""
        calls, unresolved=module.frontend_operations(config,[('client.js', "apiClient.post(buildUrl('/api/v1/ontologies')); apiClient.get(buildSemanticServiceUrl('graph', '/api/v1/ontologies')); ")])
        self.assertFalse(unresolved)
        self.assertEqual([(c['service'],c['method']) for c in calls],[('ontology','post'),('graph','get')])
        with tempfile.TemporaryDirectory() as directory:
            module.ROOT=Path(directory); module.CLIENT_ROOT=Path(directory)
            (Path(directory)/'client.js').write_text("apiClient.post(buildUrl('/api/v1/ontologies')); apiClient.get(buildSemanticServiceUrl('graph', '/api/v1/ontologies'));")
            module.CONFIG_PATH=SimpleNamespace(read_text=lambda **_:config)
            module.SERVICE_MANIFEST_PATH=SimpleNamespace(read_text=lambda **_:'{"services":[{"id":"ontology","module":"ontology.app:app"},{"id":"graph","module":"graph.app:app"}]}')
            def load(name):
                return SimpleNamespace(app=SimpleNamespace(openapi=lambda:{'paths':{'/api/v1/ontologies':{'get':{}}} if name=='ontology.app' else {}}))
            with patch.object(module.importlib,'import_module',side_effect=load):report=module.classify_contract()
        self.assertEqual(report['status'],'fail')
        self.assertEqual(len(report['unclassified']),2)

    def test_empty_frontend_inventory_cannot_pass(self):
        spec=importlib.util.spec_from_file_location('contract_audit',Path('scripts/frontend_api_contract.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            module.ROOT=Path(directory);module.CLIENT_ROOT=Path(directory)
            module.CONFIG_PATH=SimpleNamespace(read_text=lambda **_:'')
            module.SERVICE_MANIFEST_PATH=SimpleNamespace(read_text=lambda **_:'{"services":[]}')
            self.assertEqual(module.classify_contract()['status'],'fail')

    def test_current_frontend_configuration_is_inspected(self):
        spec=importlib.util.spec_from_file_location('contract_audit',Path('scripts/frontend_api_contract.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        config=module.CONFIG_PATH.read_text(encoding='utf-8')
        sources=[(str(path),path.read_text(encoding='utf-8')) for path in module.CLIENT_ROOT.rglob('*.js') if not path.name.endswith('.test.js')]
        calls,unresolved=module.frontend_operations(config,sources)
        self.assertGreater(len(calls),100)
        self.assertTrue(any(c['path']=='/api/v1/pipeline/jobs/runs' and c['service']=='data-pipeline' and c['method']=='get' for c in calls))
        self.assertTrue(any(c['path']=='/api/v1/chat' and c['service']=='agentic' and c['method']=='post' for c in calls))
        self.assertTrue(any(c['service']=='ingestion' and 'taxonomy' in c['path'] for c in calls))
        self.assertTrue(unresolved)  # dynamic call coverage must be visible
