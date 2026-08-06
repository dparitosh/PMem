from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.Services.ontology_upload_manager import OntologyUploadManager


def test_normalize_source_rows_resolves_names_and_deduplicates_properties():
    rows = [
        {
            "name": "Part",
            "concept_type": "Class",
            "namespace": "urn:parts",
            "attributes": {"code": "string"},
            "description": "A part",
        },
        {"type": "uml:Assembly", "entity_type": "Component", "attributes": {"code": "string"}},
        {"id": "FallbackId", "status": "active"},
        {"name": ""},
        "invalid",
    ]

    normalized, properties = OntologyUploadManager._normalize_source_rows(rows, "fallback")

    assert [row["name"] for row in normalized] == ["Part", "Assembly", "FallbackId"]
    assert normalized[0]["namespace"] == "urn:parts"
    assert normalized[1]["namespace"] == "fallback"
    assert properties == [
        {"class_name": "Assembly", "prop_name": "code"},
        {"class_name": "FallbackId", "prop_name": "status"},
        {"class_name": "Part", "prop_name": "code"},
        {"class_name": "Part", "prop_name": "description"},
    ]


def test_parse_source_rows_rejects_unsupported_type_without_database_access():
    with pytest.raises(ValueError, match="Unsupported file type"):
        OntologyUploadManager._parse_source_rows("unknown", b"data", Path("sample.unknown"))


def test_relationship_groups_filter_unknown_classes_and_sanitize_types():
    valid_rows = [{"name": "Part"}, {"name": "Assembly"}]
    xmi = [
        {"from_label": "Part", "to_label": "Assembly", "type": "composed-of"},
        {"from_label": "Part", "to_label": "Assembly", "type": "composed-of"},
        {"from_label": "Missing", "to_label": "Part", "type": "invalid"},
    ]
    extracted = [SimpleNamespace(source="Assembly", target="Part", relation_type="contains item")]

    groups = OntologyUploadManager._relationship_groups(valid_rows, xmi, extracted)

    assert groups == {
        "COMPOSED_OF": [{"from_label": "Part", "to_label": "Assembly"}],
        "CONTAINS_ITEM": [{"from_label": "Assembly", "to_label": "Part"}],
    }


def test_relationship_and_property_merges_preserve_counts_and_batching():
    graph = MagicMock()
    groups = {"RELATED_TO": [{"from_label": "A", "to_label": "B"}]}
    properties = [
        {"class_name": "A", "prop_name": "one"},
        {"class_name": "A", "prop_name": "two"},
        {"class_name": "B", "prop_name": "three"},
    ]

    assert OntologyUploadManager._merge_relationship_groups(graph, "demo", groups) == 1
    assert OntologyUploadManager._merge_property_rows(graph, "demo", properties, batch_size=2) == 3
    assert graph.query.call_count == 3
    assert graph.query.call_args_list[1].kwargs["params"]["rows"] == properties[:2]
    assert graph.query.call_args_list[2].kwargs["params"]["rows"] == properties[2:]


@pytest.mark.parametrize(
    ("nodes", "relationships", "expected"),
    [(0, 0, "metadata_only"), (2, 0, "loaded_empty"), (2, 1, "available")],
)
def test_availability_classifies_runtime_graph_state(nodes, relationships, expected):
    assert OntologyUploadManager._availability(nodes, relationships) == expected


def test_registry_index_normalizes_entries_and_skips_missing_prefixes():
    indexed = OntologyUploadManager._registry_index([
        {"ontology_id": "demo", "neo4j_nodes_merged": 3},
        {},
    ])

    assert list(indexed) == ["demo"]
    assert indexed["demo"]["prefix"] == "demo"
    assert indexed["demo"]["ontology_prefix"] == "demo"
    assert indexed["demo"]["source"] == "registered"
    assert indexed["demo"]["node_count"] == 3
    assert indexed["demo"]["availability"] == "metadata_only"


def test_neo4j_only_entry_normalizes_name_and_counts():
    entry = OntologyUploadManager._neo4j_only_entry({
        "prefix": "demo",
        "ontology_name": "Demo SPLM",
        "node_count": 2,
        "relationship_count": 1,
    })

    assert entry is not None
    assert entry["ontology_name"] == "Demo"
    assert entry["source"] == "neo4j"
    assert entry["availability"] == "available"
    assert OntologyUploadManager._neo4j_only_entry({"prefix": " "}) is None


def test_enrich_registry_counts_scopes_query_failures(monkeypatch):
    indexed = {
        "good": {"prefix": "good", "ontology_id": "good"},
        "bad": {"prefix": "bad", "ontology_id": "bad"},
    }

    def query(_cypher, params=None, graph=None):
        if params["prefix"] == "bad":
            raise RuntimeError("offline")
        return [{"node_count": 4, "relationship_count": 2}]

    monkeypatch.setattr(OntologyUploadManager, "_query_configured_neo4j", query)
    OntologyUploadManager._enrich_registry_counts(indexed)

    assert indexed["good"]["availability"] == "available"
    assert indexed["good"]["node_count"] == 4
    assert indexed["bad"]["availability"] == "count_failed"
    assert indexed["bad"]["count_error"] == "offline"


def test_merge_neo4j_only_entries_preserves_registered_prefix(monkeypatch):
    indexed = {"registered": {"prefix": "registered", "source": "registered"}}
    monkeypatch.setattr(
        OntologyUploadManager,
        "_query_configured_neo4j",
        lambda *args, **kwargs: [
            {"prefix": "registered", "node_count": 10},
            {"prefix": "new", "ontology_name": "New SPLM", "node_count": 1},
        ],
    )

    OntologyUploadManager._merge_neo4j_only_entries(indexed)

    assert indexed["registered"]["source"] == "registered"
    assert indexed["new"]["ontology_name"] == "New"
