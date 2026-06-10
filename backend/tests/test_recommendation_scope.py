from backend.Services.recommendation_scope import scope_values, cypher_scope_filter


def test_scope_values_accepts_namespace_fields():
    values = scope_values({
        "namespace": "http://example.com/ap242#",
        "source_namespaces": ["http://example.com/plmxml#"],
    })

    assert "http://example.com/ap242#" in values
    assert "http://example.com/plmxml#" in values


def test_cypher_scope_filter_uses_scope_values():
    clause, params = cypher_scope_filter("n", {
        "ontology_id": ["ap242"],
        "target_namespace": "http://example.com/ap242#",
    })

    assert "coalesce(n.ontology_id" in clause
    assert params["ontology_scope_values"] == ["ap242", "http://example.com/ap242#"]
