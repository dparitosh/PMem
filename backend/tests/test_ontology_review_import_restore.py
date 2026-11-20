"""Review restored import evidence without starting services or a language model."""
import json
import sys
from types import SimpleNamespace

import pytest

from backend.Services.import_task_persistence import persist_task
from backend.agentic_service.ontology_orchestrator import _instance_metadata


def restored_import(tmp_path, monkeypatch):
    path = tmp_path / 'task-1.json'
    persist_task(path, {'task_id': 'task-1', 'filename': 'part.xml',
                       'parsed_rows': [{'entity_type': 'Part', 'name': 'Bearing', 'material': 'Steel'}]}, dict)
    snapshot = json.loads(path.read_text())
    service = SimpleNamespace(_restore_task=lambda _: snapshot, _task_snapshot_path=lambda _: path)
    monkeypatch.setitem(sys.modules, 'backend.Services.unified_data_import', SimpleNamespace(UnifiedDataImportService=service))
    return path, snapshot


def test_review_retains_entity_evidence_after_service_restart(tmp_path, monkeypatch):
    restored_import(tmp_path, monkeypatch)
    metadata = _instance_metadata('task-1', None)
    assert metadata['entities'] == ['Part']
    assert 'material' in metadata['attributes']


def test_missing_rows_do_not_become_a_successful_empty_review(tmp_path, monkeypatch):
    path, snapshot = restored_import(tmp_path, monkeypatch)
    (path.parent / snapshot['_parsed_rows_file']).unlink()
    with pytest.raises(ValueError, match='retained parsed rows are unavailable'):
        _instance_metadata('task-1', None)


def test_sidecar_pointer_cannot_escape_the_selected_import(tmp_path, monkeypatch):
    path, snapshot = restored_import(tmp_path, monkeypatch)
    other = tmp_path / 'other.json'
    other.write_text('[{"entity_type":"Unrelated"}]')
    snapshot['_parsed_rows_file'] = other.name
    with pytest.raises(ValueError, match='invalid parsed row data'):
        _instance_metadata('task-1', None)


def test_changed_content_cannot_masquerade_as_retained_evidence(tmp_path, monkeypatch):
    path, snapshot = restored_import(tmp_path, monkeypatch)
    (path.parent / snapshot['_parsed_rows_file']).write_text('[{"entity_type":"Unrelated"}]')
    with pytest.raises(ValueError, match='invalid parsed row data'):
        _instance_metadata('task-1', None)


def test_legacy_sidecar_and_in_memory_rows_remain_supported(tmp_path, monkeypatch):
    path, snapshot = restored_import(tmp_path, monkeypatch)
    rows = json.loads((path.parent / snapshot.pop('_parsed_rows_file')).read_text())
    path.with_name(path.name + '.parsed_rows.json').write_text(json.dumps(rows))
    assert _instance_metadata('task-1', None)['entities'] == ['Part']
    snapshot['parsed_rows'] = [{'entity_type': 'Assembly'}]
    assert _instance_metadata('task-1', None)['entities'] == ['Assembly']

def test_internal_tracking_fields_are_not_business_mapping_terms(tmp_path, monkeypatch):
    _, snapshot = restored_import(tmp_path, monkeypatch)
    snapshot['parsed_rows'] = [{'element_type':'Part','name':'Bearing','material':'Steel','import_id':'task-1','import_row_key':'id2','uuid':'u','identity_origin':'generated','source_element_namespace':'urn:source'}]
    metadata = _instance_metadata('task-1', None)
    assert metadata['entities'] == ['Part']
    assert 'material' in metadata['attributes']
    assert not ({'import_id','import_row_key','uuid','identity_origin'} & set(metadata['attributes']))
    assert 'source_element_namespace' not in metadata['relationships']
    assert metadata['metadata'] == []


def test_names_without_types_are_not_treated_as_classes(tmp_path, monkeypatch):
    _, snapshot = restored_import(tmp_path, monkeypatch)
    snapshot['parsed_rows'] = [{'name':'Rotor Shaft 000684'}]
    assert _instance_metadata('task-1', None)['entities'] == []

def test_unmatched_terms_do_not_claim_checks_were_executed(monkeypatch):
    from backend.agentic_service.ontology_orchestrator import plan_bridge
    monkeypatch.setenv('ONTOLOGY_AGENT_LLM_ENABLED','false')
    result=plan_bridge({'entities':['Unknown']},ontology_summary={'term_index':[]})
    assert result['alignment_items'][0]['validation_checks']=={}
    assert result['alignment_items'][0]['unresolved_checks']==[]
    assert result['status']=='review_required'
