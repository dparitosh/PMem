"""Fault injection for ontology identity and PostgreSQL/filesystem boundaries."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.mesh_store import InMemoryRegistry
from backend.ontology_service.catalog import OntologyCatalog
from backend.ontology_service.intelligence import SemanticIntelligence
from backend.ingestion_service.engineering_workflow import EngineeringWorkflow


def test_conversion_capacity_rejects_before_spawn_and_releases_after_failure(monkeypatch):
    from backend.ingestion_service import conversion_process as module
    monkeypatch.setenv('ENGINEERING_CONVERSION_MAX_CONCURRENCY','1')
    module.conversion_slots.cache_clear()
    slots=module.conversion_slots()
    convert=Mock(side_effect=ValueError('synthetic conversion failure'))
    monkeypatch.setattr(module,'_convert_engineering',convert)
    try:
        assert slots.acquire(blocking=False)
        with pytest.raises(RuntimeError,match='capacity is busy'):module.convert_engineering()
        convert.assert_not_called()
        slots.release()
        with pytest.raises(ValueError):module.convert_engineering()
        assert slots.acquire(blocking=False)
        slots.release()
    finally:
        module.conversion_slots.cache_clear()


def test_similar_generated_iris_are_not_duplicate_resource_identities(tmp_path, monkeypatch):
    intelligence=SemanticIntelligence(tmp_path,registry=InMemoryRegistry())
    similarity=Mock(side_effect=AssertionError('IRI identity must not use string similarity'))
    monkeypatch.setattr('backend.ontology_service.intelligence.detect_duplicates',similarity)
    entities=[{'id':f'https://example.test/sysml#magicdraw_class_000{i}'} for i in (1,2)]
    report=intelligence.quality_gate(entities=entities,deduplicate=True,conflict_property=None,
                                     deduplication_mode='resource_identity')
    assert report['publish_recommended'] is True
    assert report['duplicates']==[] and report['semantic_similarity_checked'] is False
    assert report['consistency_verified'] is False
    repeated=intelligence.quality_gate(entities=[entities[0],entities[0]],deduplicate=True,
        conflict_property=None,deduplication_mode='resource_identity')
    assert repeated['publish_recommended'] is False


def test_resource_identity_review_includes_urns_and_excludes_blank_nodes():
    entities=EngineeringWorkflow._governance_entities(
        '<urn:example:Class> <urn:example:property> [ <urn:example:property> "value" ] .')
    assert [item['id'] for item in entities]==['urn:example:Class']


def test_committed_postgres_metadata_survives_disk_mirror_failure(tmp_path,monkeypatch,caplog):
    monkeypatch.setenv('DEPO_DATABASE_URL','postgresql://unused/test')
    registry=InMemoryRegistry()
    catalog=OntologyCatalog(root=tmp_path,registry=registry)
    metadata={'ontology_id':'example_abc','lifecycle_status':'approved'}
    monkeypatch.setattr('backend.ontology_service.catalog.os.replace',Mock(side_effect=PermissionError('private-path')))
    assert catalog._save_metadata(metadata)==metadata
    assert registry.get('example_abc')==metadata
    assert 'disk mirror unavailable' in caplog.text and 'private-path' not in caplog.text
    assert list(tmp_path.rglob('*.tmp'))==[]


def test_postgres_failure_is_not_disguised_as_success(tmp_path,monkeypatch):
    monkeypatch.setenv('DEPO_DATABASE_URL','postgresql://unused/test')
    registry=Mock(put=Mock(side_effect=RuntimeError('database unavailable')))
    catalog=OntologyCatalog(root=tmp_path,registry=registry)
    with pytest.raises(RuntimeError):catalog._save_metadata({'ontology_id':'example_abc'})
    assert not (tmp_path/'example_abc'/'metadata.json').exists()


def test_metadata_mirror_replacement_is_complete_json(tmp_path,monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL',raising=False)
    monkeypatch.delenv('DATABASE_URL',raising=False)
    catalog=OntologyCatalog(root=tmp_path)
    before={'ontology_id':'example_abc','lifecycle_status':'draft'}
    after={**before,'lifecycle_status':'approved'}
    catalog._save_metadata(before)
    catalog._save_metadata(after)
    assert json.loads((tmp_path/'example_abc'/'metadata.json').read_text())==after
    monkeypatch.setattr('backend.ontology_service.catalog.os.replace',Mock(side_effect=PermissionError()))
    with pytest.raises(PermissionError):catalog._save_metadata(before)
    assert json.loads((tmp_path/'example_abc'/'metadata.json').read_text())==after
