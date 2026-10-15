import ast
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import Mock, MagicMock, patch
from fastapi import HTTPException
from backend.depo_platform import metadata_service


class MetadataDeliveryTests(unittest.TestCase):
    def test_storage_mode_is_explicit_and_invalid_modes_fail(self):
        with patch.dict(os.environ,{},clear=True): self.assertFalse(metadata_service.enabled())
        with patch.dict(os.environ,{'DEPO_METADATA_STORAGE':'postgres'}): self.assertTrue(metadata_service.enabled())
        with patch.dict(os.environ,{'DEPO_METADATA_STORAGE':'invalid'}), self.assertRaises(RuntimeError): metadata_service.enabled()

    def test_stale_metadata_edit_cannot_overwrite_new_revision(self):
        repository=SimpleNamespace(get=lambda _: {'asset_id':'part','name':'Current','revision':2},save=Mock())
        with patch.object(metadata_service,'repository',return_value=repository), self.assertRaises(HTTPException) as error:
            metadata_service.update('part',{'name':'Stale'},'verified',expected_revision=1)
        self.assertEqual(error.exception.status_code,409)
        repository.save.assert_not_called()

    def test_graph_failure_does_not_acknowledge_metadata_outbox(self):
        from backend.depo_platform.metadata_projection import project_pending
        db=MagicMock(); db.__enter__.return_value=db
        cursor=db.cursor.return_value.__enter__.return_value
        event={'before':None,'after':{'asset_id':'part','name':'Part'},'actor':'verified'}
        cursor.fetchall.return_value=[('event','part',1,event)]
        store=SimpleNamespace(_connect=lambda:db)
        graph=SimpleNamespace(query=Mock(side_effect=[None,RuntimeError('graph unavailable')]))
        module=ModuleType('backend.core.graph'); module.graph=graph
        with patch.object(metadata_service,'enabled',return_value=True), patch.object(metadata_service,'repository',return_value=SimpleNamespace(store=store)), patch.dict('sys.modules',{'backend.core.graph':module}), self.assertRaises(RuntimeError):
            project_pending()
        self.assertFalse(any('UPDATE depo_metadata_outbox' in call.args[0] for call in cursor.execute.call_args_list))

    def test_context_deadline_survives_sync_adapter_thread(self):
        from backend.core.sync_async import call_async
        from backend.depo_platform.operations import OperationContext,operation_scope,current_operation
        async def read(): return current_operation().operation_id
        async def run():
            with operation_scope(OperationContext('retained','2099-01-01T00:00:00+00:00')):
                return call_async(read)
        self.assertEqual(asyncio.run(run()),'retained')

    def test_context_deadline_survives_stream_adapter_thread(self):
        from backend.core.sync_async import iterate_async
        from backend.depo_platform.operations import OperationContext,operation_scope,current_operation
        async def values(): yield current_operation().operation_id
        with operation_scope(OperationContext('stream','2099-01-01T00:00:00+00:00')):
            self.assertEqual(list(iterate_async(values)),['stream'])


class ContractBundleTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('service_contract_export',Path('scripts/export_service_openapi.py'))
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def test_collection_checks_all_services_and_rejects_partial_success(self):
        module=self.module(); services=[{'id':str(i)} for i in range(10)]; visited=[]
        def load(service):
            visited.append(service['id'])
            if service['id']=='3': raise ImportError('missing dependency')
            return {'openapi':'3.0.3','paths':{}}
        with self.assertRaises(ValueError): module.collect(services,load)
        self.assertEqual(len(visited),10)

    def test_complete_bundle_has_matching_hashes_and_partial_bundle_is_refused(self):
        module=self.module()
        services=json.loads(Path('infra/deployment/services.json').read_text())['services']
        documents={service['id']:{'openapi':'3.0.3','paths':{}} for service in services}
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): module.export(directory,services,{})
            self.assertEqual(list(Path(directory).iterdir()),[])
            with patch.object(module.subprocess,'check_output',side_effect=['commit\n','']):
                bundle=module.export(directory,services,documents)
            manifest=json.loads((bundle/'manifest.json').read_text())
            self.assertEqual(len(manifest['services']),10)
            for service in manifest['services']:
                self.assertEqual(service['sha256'],hashlib.sha256((bundle/service['file']).read_bytes()).hexdigest())
