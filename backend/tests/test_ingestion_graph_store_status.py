from backend.ingestion_service.neo4j_writer import GraphStoreConfig


def test_non_neo4j_graph_stores_are_reported_as_adapter_gated(monkeypatch):
    monkeypatch.setenv("SEMANTIC_GRAPH_PROVIDER", "oracle")
    status = GraphStoreConfig.from_env().status()
    assert status["provider"] == "oracle"
    assert status["write_supported"] is False
    assert "ORACLE_SEMANTIC_GRAPH_DSN" in status["required_configuration"]
