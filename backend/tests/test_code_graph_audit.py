from tools.code_graph_audit import audit


def test_code_audit_emits_a_resolved_hierarchy_with_javascript_symbols():
    report = audit()
    hierarchy = report["hierarchy"]
    node_ids = {node["id"] for node in hierarchy["nodes"]}

    assert hierarchy["root"] in node_ids
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in hierarchy["edges"])
    assert any(node["type"] == "function" and node.get("path", "").endswith("App.js") for node in hierarchy["nodes"])
