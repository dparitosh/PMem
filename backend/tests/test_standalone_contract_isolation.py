import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest


class StandaloneContractTests(unittest.TestCase):
    def test_aggregate_only_route_cannot_make_standalone_contract_pass(self):
        spec=importlib.util.spec_from_file_location('contract_audit',Path('scripts/frontend_api_contract.py'))
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.CONFIG_PATH=SimpleNamespace(read_text=lambda **_: "process.env.TEST_URL || '/aggregate-only'")
        module.SERVICE_MANIFEST_PATH=SimpleNamespace(read_text=lambda **_: '{"services":[{"id":"ontology","module":"backend.ontology_service.app:app"}]}')
        def load(name):
            paths={'/aggregate-only':{}} if name=='backend.main' else {'/standalone':{}}
            return SimpleNamespace(app=SimpleNamespace(openapi=lambda:{'paths':paths}))
        with patch.object(module.importlib,'import_module',side_effect=load):
            report=module.classify_contract()
        self.assertEqual(report['status'],'fail')
        self.assertEqual(report['unclassified'],['/aggregate-only'])
