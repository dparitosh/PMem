from __future__ import annotations

import pytest

from backend.ontology_service.catalog import OntologyCatalog


def test_catalog_validates_rdf_and_records_review_lifecycle(tmp_path):
    catalog = OntologyCatalog(root=tmp_path / "catalog")
    record = catalog.register(
        content=b'@prefix ex: <https://example.test/> . ex:Part ex:label "Part" .',
        filename="part.ttl", ontology_name="Part", prefix="part",
    )

    assert record["lifecycle_status"] == "draft"
    assert record["validation"] == {"status": "passed", "rdf_format": "turtle", "triple_count": 1}
    review = catalog.transition(ontology_id=record["ontology_id"], target="in_review", actor="steward")
    approved = catalog.transition(ontology_id=record["ontology_id"], target="approved", actor="steward")
    assert review["lifecycle_status"] == "in_review"
    assert approved["lifecycle_status"] == "approved"


def test_catalog_rejects_invalid_ontology_syntax(tmp_path):
    catalog = OntologyCatalog(root=tmp_path / "catalog")
    with pytest.raises(ValueError, match="parsing failed"):
        catalog.register(content=b"not turtle [", filename="broken.ttl", ontology_name="Broken", prefix="broken")


def test_catalog_accepts_turtle_serialized_owl(tmp_path):
    catalog = OntologyCatalog(root=tmp_path / "catalog")
    record = catalog.register(
        content=b'@prefix owl: <http://www.w3.org/2002/07/owl#> . <https://example.test/onto> a owl:Ontology .',
        filename="ontology.owl", ontology_name="Example", prefix="example",
    )
    assert record["validation"]["rdf_format"] == "turtle"


def test_legacy_catalog_analytics_backfill_is_additive_and_keeps_draft(tmp_path):
    catalog = OntologyCatalog(root=tmp_path / "catalog")
    record = catalog.register(
        content=(b'@prefix owl: <http://www.w3.org/2002/07/owl#> . '
                 b'@prefix ex: <https://example.test/> . ex:Part a owl:Class . '
                 b'ex:hasPart a owl:ObjectProperty .'),
        filename="legacy.ttl", ontology_name="Legacy", prefix="legacy",
    )
    legacy = catalog.get(record["ontology_id"])
    for field in ("lifecycle_status", "semantic_completeness", "statistics", "validation", "lifecycle_events"):
        legacy.pop(field, None)
    catalog._save_metadata(legacy)

    result = catalog.backfill_analytics(ontology_ids=[record["ontology_id"]], actor="steward")

    assert result["updated"] == 1
    updated = catalog.get(record["ontology_id"])
    assert updated["lifecycle_status"] == "draft"
    assert updated["semantic_completeness"] == "unknown"
    assert updated["statistics"]["classes"] == 1
    assert updated["statistics"]["object_properties"] == 1
    assert "no approval or publication" in updated["lifecycle_events"][-1]["reason"]


def test_invalid_legacy_artifact_cannot_be_approved(tmp_path):
    catalog = OntologyCatalog(root=tmp_path)
    record = catalog.adopt_legacy(ontology_id="legacy", content=b"broken [", filename="old.ttl", ontology_name="Old", prefix="old")
    catalog.transition(ontology_id=record["ontology_id"], target="in_review", actor="steward")
    with pytest.raises(ValueError, match="parsing failed"):
        catalog.transition(ontology_id="legacy", target="approved", actor="steward")
    assert catalog.get("legacy")["lifecycle_status"] == "in_review"


def test_registration_rejects_reserved_metadata_filename(tmp_path):
    instance = OntologyCatalog(root=tmp_path / 'reserved')
    with pytest.raises(ValueError):
        instance.register(content=b'{}', filename='metadata.json', ontology_name='Example', prefix='ex')


def test_registration_rejects_identity_override(tmp_path):
    instance = OntologyCatalog(root=tmp_path / 'override')
    with pytest.raises(ValueError):
        instance.register(content=b'@prefix ex: <https://example.test/> . ex:A ex:p ex:B .',
                          filename='example.ttl', ontology_name='Example', prefix='ex',
                          extra_metadata={'artifact_path': '/outside'})


def test_registration_blocks_remote_jsonld_context():
    with pytest.raises(ValueError):
        OntologyCatalog._parse_ontology(b'{"@context":"https://remote.invalid/context", "@id":"https://example.test/A"}', 'example.jsonld')


def test_registration_blocks_external_xml_entities():
    with pytest.raises(ValueError):
        OntologyCatalog._parse_ontology(b'<!DOCTYPE rdf [<!ENTITY file SYSTEM "file:///secret">]><rdf>&file;</rdf>', 'example.rdf')
