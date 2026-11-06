import pytest

from backend.ceim.contract import contract
from backend.ceim.normalization import normalize_record
from backend.ceim.resolution import analyze_entities


def test_ap242_entity_normalization_keeps_mapping_provenance():
    entity = contract.normalize_entity(
        standard="ap242",
        record={"source_type": "product_definition", "source_id": "PD-1", "attributes": {"name": "Motor cover"}},
    )
    assert entity["ceim_type"] == "Product"
    assert entity["properties"]["name"] == "Motor cover"
    assert entity["provenance"]["mapping_pack"] == "ap242-core"


def test_normalized_batch_rejects_stale_or_mixed_mapping_evidence():
    entity = contract.normalize_entity(
        standard="ap242",
        record={"source_type": "product_definition", "source_id": "PD-1", "attributes": {"name": "Motor cover"}},
    )
    assert contract.validate_mapping_evidence(standard="ap242", entities=[entity], relationships=[])["mapping_pack"] == "ap242-core"
    entity["provenance"]["mapping_version"] = "obsolete"
    with pytest.raises(ValueError, match="mapping_version"):
        contract.validate_mapping_evidence(standard="ap242", entities=[entity], relationships=[])


def test_unknown_source_type_is_rejected_instead_of_guessed():
    with pytest.raises(ValueError, match="No CEIM entity mapping"):
        contract.normalize_entity(standard="qif", record={"source_type": "Unknown", "source_id": "1"})


def test_ceim_projection_retains_external_id_and_passes_shapes():
    entity = contract.normalize_entity(
        standard="reqif",
        record={"source_type": "SPEC-OBJECT", "source_id": "REQ-1", "attributes": {"LONG-NAME": "Torque"}},
    )
    report = contract.validate_projection(entities=[entity], relationships=[])
    assert report["conforms"] is True
    assert report["triple_count"] >= 2
    assert report["shape_summary"]["node_shapes"] >= 2
    assert report["shape_summary"]["property_shapes"] >= 1


def test_relationship_projection_retains_declared_source_key():
    entity = contract.normalize_entity(
        standard="reqif",
        record={"source_type": "SPEC-OBJECT", "source_id": "REQ-1", "attributes": {"LONG-NAME": "Torque"}},
    )
    relationship = contract.normalize_relationship(
        standard="reqif", record={"source_type": "SPEC-RELATION", "source_id": "REQ-1", "target_id": "REQ-1"},
    )
    assert relationship["provenance"]["source_key"] == "mapping:SPEC-RELATION"
    assert "sourceKey" in contract.turtle_projection(entities=[entity], relationships=[relationship])


def test_source_normalization_records_text_date_and_number_evidence():
    normalized, evidence = normalize_record({"name": "  M\u00f6tor\u00a0Cover ", "inspection_date": "2026-09-04T10:00:00Z", "length": "1,200.00"})
    assert normalized == {"name": "M\u00f6tor Cover", "inspection_date": "2026-09-04T10:00:00+00:00", "length": "1200"}
    assert {item["rule"] for item in evidence} == {"unicode_text", "iso8601_datetime", "decimal"}


def test_exact_duplicates_are_merged_with_all_source_provenance():
    entity = contract.normalize_entity(standard="qif", record={"source_type": "Part", "source_id": "P-1", "attributes": {"name": "Rotor"}})
    result = analyze_entities([entity, entity])
    assert result["blocking"] is False
    assert len(result["entities"]) == 1
    assert len(result["entities"][0]["provenance"]["merged_source_provenance"]) == 2


def test_conflicting_duplicate_blocks_rdf_construction_and_prov_is_emitted():
    first = contract.normalize_entity(standard="qif", record={"source_type": "Part", "source_id": "P-1", "attributes": {"name": "Rotor"}})
    conflicting = contract.normalize_entity(standard="qif", record={"source_type": "Part", "source_id": "P-1", "attributes": {"name": "Stator"}})
    with pytest.raises(ValueError, match="Entity-resolution conflicts"):
        contract.to_rdf(entities=[first, conflicting], relationships=[])
    graph = contract.to_rdf(entities=[first], relationships=[], decision={"approved_by": "steward", "semantic_release": {"asset_id": "ceim", "version": "0.1.0"}})
    assert any(str(predicate) == "http://www.w3.org/ns/prov#wasDerivedFrom" for _, predicate, _ in graph)
    assert any(str(predicate) == "http://www.w3.org/ns/prov#wasAssociatedWith" for _, predicate, _ in graph)
