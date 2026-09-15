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


def test_invalid_legacy_artifact_cannot_be_approved(tmp_path):
    catalog = OntologyCatalog(root=tmp_path)
    record = catalog.adopt_legacy(ontology_id="legacy", content=b"broken [", filename="old.ttl", ontology_name="Old", prefix="old")
    catalog.transition(ontology_id=record["ontology_id"], target="in_review", actor="steward")
    with pytest.raises(ValueError, match="parsing failed"):
        catalog.transition(ontology_id="legacy", target="approved", actor="steward")
    assert catalog.get("legacy")["lifecycle_status"] == "in_review"
