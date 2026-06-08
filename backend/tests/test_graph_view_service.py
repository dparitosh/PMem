from backend.Services.graph_view_service import GraphViewService
from pathlib import Path


def test_rows_to_graph_deduplicates_nodes_and_relationships():
    rows = [
        {
            "n": {"elementId": "n1", "labels": ["A"], "properties": {"name": "A1"}},
            "r": {"elementId": "r1", "type": "REL", "start": "n1", "end": "n2", "properties": {}},
            "m": {"elementId": "n2", "labels": ["B"], "properties": {"name": "B1"}},
        },
        {
            "n": {"elementId": "n1", "labels": ["A"], "properties": {"name": "A1"}},
            "r": {"elementId": "r1", "type": "REL", "start": "n1", "end": "n2", "properties": {}},
            "m": {"elementId": "n2", "labels": ["B"], "properties": {"name": "B1"}},
        },
    ]

    graph = GraphViewService.rows_to_graph(rows)

    assert graph["counts"]["nodes"] == 2
    assert graph["counts"]["relationships"] == 1
    assert {node["elementId"] for node in graph["nodes"]} == {"n1", "n2"}
    assert graph["relationships"][0]["elementId"] == "r1"


def test_contextual_subgraph_search_uses_labels_and_properties(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_contextual_subgraph(search="rotor", limit=25)

    assert "labels(seed)" in captured["cypher"]
    assert "properties(seed)" in captured["cypher"]
    assert captured["params"]["search"] == "rotor"
    assert captured["params"]["limit"] == 25


def test_virtual_ontology_view_uses_schema_nodes_and_relationships(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_virtual_ontology_view(prefix="ap239", limit=120)

    assert "labels(n)" in captured["cypher"]
    assert "labels(m)" in captured["cypher"]
    assert "type(r) = 'DOMAIN'" in captured["cypher"]
    assert "type(r) = 'RANGE'" in captured["cypher"]
    assert "type(r) = 'SUBCLASS_OF'" in captured["cypher"]
    assert "NOT EXISTS" in captured["cypher"]
    assert captured["params"]["prefix"] == "ap239"
    assert captured["params"]["limit"] == 120
    assert captured["params"]["relationship_slice_limit"] > 0
    assert captured["params"]["isolated_limit"] > 0
    assert "SUBCLASS_OF" in captured["params"]["schema_relationship_types"]
    assert "DOMAIN" in captured["params"]["schema_relationship_types"]
    assert "RANGE" in captured["params"]["schema_relationship_types"]


def test_extract_xsd_named_subclass_rows_reads_extension_hierarchy(tmp_path):
    xsd_path = Path(tmp_path) / "sample.xsd"
    xsd_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:complexType name="BaseType" />
  <xs:complexType name="ChildType">
    <xs:complexContent>
      <xs:extension base="BaseType" />
    </xs:complexContent>
  </xs:complexType>
  <xs:complexType name="AnotherChild">
    <xs:simpleContent>
      <xs:extension base="tns:BaseType" xmlns:tns="urn:test" />
    </xs:simpleContent>
  </xs:complexType>
</xs:schema>
""",
        encoding="utf-8",
    )

    rows = GraphViewService._extract_xsd_named_subclass_rows(
        xsd_path,
        {
            "BaseType": "urn:test#BaseType",
            "ChildType": "urn:test#ChildType",
            "AnotherChild": "urn:test#AnotherChild",
        },
    )

    assert rows == [
        {"child_uri": "urn:test#AnotherChild", "parent_uri": "urn:test#BaseType"},
        {"child_uri": "urn:test#ChildType", "parent_uri": "urn:test#BaseType"},
    ]
