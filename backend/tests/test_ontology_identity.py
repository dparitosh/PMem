from backend.Services.ontology_identity import normalize_ontology_entry, normalize_ontology_entries


def test_normalize_ontology_entry_fills_canonical_fields():
    row = {
        "ontology_id": "ap242_123",
        "ontology_name": "AP242 Ontology",
        "source_namespace": "http://example.com/ap242#",
        "node_count": "12",
        "relationship_count": None,
    }

    normalized = normalize_ontology_entry(row)

    assert normalized["ontology_id"] == "ap242_123"
    assert normalized["id"] == "ap242_123"
    assert normalized["prefix"] == "ap242_123"
    assert normalized["ontology_prefix"] == "ap242_123"
    assert normalized["name"] == "AP242 Ontology"
    assert normalized["namespace"] == "http://example.com/ap242#"
    assert normalized["source_namespace"] == "http://example.com/ap242#"
    assert normalized["node_count"] == 12
    assert normalized["relationship_count"] == 0


def test_normalize_ontology_entries_accepts_sparse_registry_rows():
    rows = normalize_ontology_entries([
        {"prefix": "plmxml", "name": "PLMXML"},
        {"ontology_id": "sysml", "ontology_name": "SysML"},
    ])

    assert rows[0]["ontology_id"] == "plmxml"
    assert rows[0]["ontology_name"] == "PLMXML"
    assert rows[1]["prefix"] == "sysml"
    assert rows[1]["ontology_name"] == "SysML"
