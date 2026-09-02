from backend.graph_service.neo4j_publisher import Neo4jPublisher


def test_live_projection_is_consumed_by_semantica_analytics(monkeypatch):
    publisher = Neo4jPublisher()
    monkeypatch.setattr(
        publisher,
        "projection",
        lambda **_: {
            "ontology_id": "parts", "nodes": [
                {"id": "Part", "label": "Part", "type": "class"},
                {"id": "Assembly", "label": "Assembly", "type": "class"},
            ],
            "edges": [{"source": "Assembly", "target": "Part", "type": "SUBCLASS_OF"}],
            "truncated": False,
        },
    )

    result = publisher.analytics(ontology_id="parts")

    assert result["analytics"]["metrics"]["num_nodes"] == 2
    assert result["analytics"]["connectivity"]["is_connected"] is True


def test_explorer_projection_uses_the_stable_browser_graph_contract(monkeypatch):
    publisher = Neo4jPublisher()
    monkeypatch.setattr(
        publisher,
        "projection",
        lambda **_: {
            "ontology_id": "parts",
            "nodes": [{"id": "Assembly", "label": "Assembly", "type": "class"}],
            "edges": [{"source": "Assembly", "target": "Assembly", "type": "SUBCLASS_OF"}],
            "truncated": False,
        },
    )

    result = publisher.explorer_projection(ontology_id="parts", limit=10)

    assert result["view"]["type"] == "ontology"
    assert result["nodes"][0]["elementId"] == "Assembly"
    assert result["relationships"][0]["start"] == "Assembly"
    assert result["counts"] == {"nodes": 1, "relationships": 1}
