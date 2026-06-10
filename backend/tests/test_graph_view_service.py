from backend.Services.graph_view_service import GraphViewService


def test_resolve_ontology_prefix_from_registry_id(monkeypatch):
    def fake_run(_cypher, params):
        assert params == {"token": "ap242_1781013408"}
        return [{"prefix": "ap242"}]

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    assert GraphViewService._resolve_ontology_prefix("ap242_1781013408") == "ap242"


def test_resolve_ontology_prefix_keeps_prefix_when_no_match(monkeypatch):
    monkeypatch.setattr(GraphViewService, "_run", staticmethod(lambda _cypher, _params: []))

    assert GraphViewService._resolve_ontology_prefix("ap242") == "ap242"
