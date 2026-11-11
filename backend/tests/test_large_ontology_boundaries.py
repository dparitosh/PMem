from pathlib import Path
import pickle
from types import SimpleNamespace
from unittest.mock import patch, Mock

import pytest

from backend.ontology_service.catalog import OntologyCatalog
from backend.ingestion_service.engineering_workflow import EngineeringWorkflow
from backend.ontology_service.merge_background import validation_child


def test_oversized_catalog_artifact_keeps_limit_error_before_parsing():
    with patch('backend.ontology_service.catalog.ontology_upload_limit', return_value=5), \
         patch('backend.ontology_service.catalog.Graph') as graph:
        with pytest.raises(ValueError, match='ONTOLOGY_MAX_UPLOAD_BYTES'):
            OntologyCatalog._parse_ontology(b'123456', 'large.ttl')
        graph.assert_not_called()


def test_retained_oversized_artifact_rejected_before_open(tmp_path):
    folder = tmp_path / 'large'; folder.mkdir()
    path = folder / 'ontology.ttl'; path.write_bytes(b'123456')
    catalog = object.__new__(OntologyCatalog)
    catalog.root = tmp_path
    catalog.get = lambda _: {'artifact_path': str(path)}
    with patch('backend.ontology_service.catalog.ontology_upload_limit', return_value=5), \
         patch.object(Path, 'open') as opened:
        with pytest.raises(ValueError, match='Retained ontology artifact exceeds'):
            catalog.read_artifact('large')
        opened.assert_not_called()


@pytest.mark.asyncio
async def test_generated_artifact_limit_stops_before_quality_or_registration():
    class Converter:
        def convert(self, **kwargs):
            return {'ontology': {'turtle': '\u00e9\u00e9\u00e9'}}
    with patch('backend.depo_platform.upload_limits.ontology_upload_limit', return_value=5), \
         patch('backend.ingestion_service.engineering_workflow.service_bearer_headers') as credentials, \
         patch('httpx.AsyncClient') as client:
        with pytest.raises(ValueError, match='Generated ontology is 6 bytes'):
            await EngineeringWorkflow(Converter()).run(filename='large.xsd', content=b'x')
        credentials.assert_not_called()
        client.assert_not_called()


def test_merge_child_decodes_from_file_without_captured_byte_copy():
    def popen(*args, **kwargs):
        assert pickle.load(kwargs['stdin']) == {'input': 'fixture'}
        pickle.dump({'ok': True}, kwargs['stdout'])
        return SimpleNamespace(poll=lambda: 0, wait=lambda: 0, returncode=0)
    with patch('subprocess.Popen', side_effect=popen), patch('pickle.loads', side_effect=AssertionError('byte copy')):
        assert validation_child({'input': 'fixture'}, Mock(), 10) == {'ok': True}


def test_merge_child_limit_is_checked_before_decoding():
    def popen(*args, **kwargs):
        kwargs['stdout'].write(b'123456')
        return SimpleNamespace(poll=lambda: 0, wait=lambda: 0, returncode=0)
    with patch('subprocess.Popen', side_effect=popen), \
         patch('backend.ontology_service.merge_background.child_result_limit', return_value=5), \
         patch('pickle.load') as load:
        with pytest.raises(ValueError, match='configured size limit'):
            validation_child({}, Mock(), 10)
        load.assert_not_called()
