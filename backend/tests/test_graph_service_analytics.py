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
