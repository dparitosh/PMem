"""Actual parser code, trusted XML fixtures, stub CEIM and HTTP boundaries."""
import ast
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from backend.Services.import_completeness import require_complete_archimate


def load_source(path, namespace, excluded=()):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if not isinstance(node, ast.ImportFrom) or node.module not in excluded]
    exec(compile(tree, path, 'exec'), namespace)
    return namespace


class MbseFixes(unittest.TestCase):
    def setUp(self):
        self.adapter = load_source('backend/ceim/mbse_adapter.py', {'ET': ET, 'contract': SimpleNamespace(version='1', normalize_entity=lambda **kw: kw['record'], normalize_relationship=lambda **kw: kw['record'])}, ('defusedxml', 'contract'))['mbse_to_ceim_batch']
        self.archimate = load_source('backend/Services/archimate_service.py', {'ET': ET}, ('defusedxml',))['parse_archimate_model_exchange']

    def test_invalid_document_ids_and_types_are_validation_errors(self):
        for data in [None, 1, [{'@id': ['bad']}], [{'@id': 'r', '@type': ['a', 'b']}], [{'@id': 'r', 'owner': {}}]]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.adapter(json.dumps(data).encode(), version='2')

    def test_single_type_array_and_reference_direction(self):
        batch = self.adapter(json.dumps([{'@id': 'r', '@type': ['RequirementUsage']}, {'@id': 'b', '@type': 'PartUsage'}, {'@id': 'd', '@type': ['SatisfyRequirementUsage'], 'source': {'elementId': 'b'}, 'target': {'@id': 'r'}}]).encode(), version='2')
        self.assertEqual(batch['relationships'][0]['source_type'], 'SATISFIES')
        self.assertEqual(batch['entities'][0]['source_type'], 'Requirement')

    def test_archimate_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.archimate(b'<model><element identifier="a"/><element identifier="a"/></model>')

    def test_preview_retains_diagnostics_but_commit_blocks(self):
        _, stats = self.archimate(b'<model><element identifier="a"/><relationship identifier="r" source="a" target="missing"/></model>')
        self.assertEqual(stats['unresolved_relationship_count'], 1)
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            require_complete_archimate({'stats': stats})
        require_complete_archimate({'stats': {'source_format': 'archimate', 'unresolved_relationship_count': 0}})

    def test_legacy_archimate_metadata_blocks_commit(self):
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            require_complete_archimate({'stats': {'file_format': 'ArchiMate', 'unresolved_relationship_count': 1}})

    def test_repository_probe_validation(self):
        from backend.Services.sysml_v2_connector_service import SysMLV2ConnectorConfig, SysMLV2ConnectorService
        cfg = SysMLV2ConnectorConfig(True, 'https://repo.example', 'key', 'p', '', 'c', 100, 10)
        self.assertTrue(cfg.configured)
        for invalid_url in ['http://[bad', 'http://user:secret@repo.example', 'not-a-url']:
            invalid = SysMLV2ConnectorConfig(True, invalid_url, 'key', 'p', '', 'c', 100, 10)
            status = SysMLV2ConnectorService(invalid).status()
            self.assertEqual(status['status'], 'not_configured')
            self.assertEqual(status['base_url'], '')
        self.assertFalse(SysMLV2ConnectorConfig(True, 'https://repo.example?token=bad', 'key', 'p', '', 'c', 100, 10).configured)
        for raw in [b'not JSON', b'{"error":"bad"}', b'x' * (1024 * 1024 + 1)]:
            response = SimpleNamespace(read=lambda limit, raw=raw: raw)
            class Context:
                def __enter__(self): return response
                def __exit__(self, *args): pass
            opener = SimpleNamespace(open=lambda *args, **kw: Context())
            with patch('backend.Services.sysml_v2_connector_service.urllib_request.build_opener', return_value=opener):
                self.assertEqual(SysMLV2ConnectorService(cfg).probe_projects()['probe_status'], 'failed')

    def test_snapshot_total_budget_across_pages(self):
        class Response:
            links = {'next': {'url': '?page[after]=next'}}
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def raise_for_status(self): pass
            async def aiter_bytes(self): yield b'[{"@id":"abcdefghijklmnop"}]'
        class Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def stream(self, *args, **kw): return Response()
        tree = ast.parse(Path('backend/ingestion_service/sysml_repository.py').read_text(encoding='utf-8'))
        tree.body = [node for node in tree.body if not (isinstance(node, ast.Import) and any(alias.name == 'httpx' for alias in node.names)) and not (isinstance(node, ast.ImportFrom) and node.module == 'backend.Services.sysml_v2_connector_service')]
        namespace = {'httpx': SimpleNamespace(AsyncClient=Client)}
        exec(compile(tree, '<actual snapshot reader>', 'exec'), namespace)
        cfg = SimpleNamespace(enabled=True, base_url='https://repo.example', project_id='p', commit_id='c', page_size=10, token='key', request_timeout_seconds=1)
        with patch.dict(os.environ, {'SYSML_V2_MAX_SNAPSHOT_BYTES': '40', 'DEPO_MAX_INGEST_BYTES': '100'}), self.assertRaisesRegex(ValueError, 'aggregate'):
            asyncio.run(namespace['read_snapshot'](cfg))


if __name__ == '__main__': unittest.main()
