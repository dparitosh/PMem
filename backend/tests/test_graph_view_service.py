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


def test_metadata_like_filter_uses_structural_signals_not_id_prefix():
    assert GraphViewService._is_metadata_like_node(
        {
            "labels": ["Individual"],
            "properties": {"name": "ID1234", "semantic_role": "entity"},
        }
    ) is False
    assert GraphViewService._is_metadata_like_node(
        {
            "labels": ["Form"],
            "properties": {"name": "MasterForm", "semantic_role": "metadata"},
        }
    ) is True


def test_individual_filter_accepts_plmxml_domain_instance_labels():
    graph = {
        "nodes": [
            {"elementId": "p1", "labels": ["Product"], "properties": {"name": "Part A"}},
            {"elementId": "u1", "labels": ["UserData"], "properties": {"semantic_role": "metadata"}},
            {"elementId": "o1", "labels": ["Occurrence"], "properties": {"name": "Occ A"}},
            {"elementId": "c1", "labels": ["OntologyClass"], "properties": {"name": "Class A"}},
        ],
        "relationships": [
            {"elementId": "r1", "type": "RELATED_TO", "start": "p1", "end": "o1", "properties": {}},
            {"elementId": "r2", "type": "RELATED_TO", "start": "p1", "end": "u1", "properties": {}},
            {"elementId": "r3", "type": "RELATED_TO", "start": "p1", "end": "c1", "properties": {}},
        ],
    }

    filtered = GraphViewService._filter_graph_nodes(graph, only_individual_nodes=True)

    assert [node["elementId"] for node in filtered["nodes"]] == ["o1", "p1"]
    assert [rel["elementId"] for rel in filtered["relationships"]] == ["r1"]


def test_individual_filter_retains_stpx_cad_business_objects_with_id_names():
    graph = {
        "nodes": [
            {
                "elementId": "part-1",
                "labels": ["PART"],
                "properties": {
                    "name": "id116",
                    "external_id": "id116",
                    "semantic_role": "product",
                    "is_cad_business_object": True,
                },
            },
            {
                "elementId": "meta-1",
                "labels": ["NAME"],
                "properties": {"name": "id117"},
            },
            {
                "elementId": "view-1",
                "labels": ["PART_VIEW"],
                "properties": {
                    "name": "id118",
                    "semantic_role": "representation",
                    "is_cad_business_object": True,
                },
            },
        ],
        "relationships": [
            {"elementId": "r1", "type": "REFERENCES", "start": "part-1", "end": "view-1", "properties": {}},
            {"elementId": "r2", "type": "PARENT_OF", "start": "part-1", "end": "meta-1", "properties": {}},
        ],
    }

    filtered = GraphViewService._filter_graph_nodes(graph, only_individual_nodes=True)

    assert [node["elementId"] for node in filtered["nodes"]] == ["part-1", "view-1"]
    assert [rel["elementId"] for rel in filtered["relationships"]] == ["r1"]


def test_rows_to_graph_preserves_traversal_hint_and_normalizes_relationship_type():
    graph = GraphViewService.rows_to_graph(
        [
            {
                "n": {
                    "elementId": "n1",
                    "labels": ["Product"],
                    "properties": {"name": "Pump"},
                    "can_traverse": True,
                },
                "m": {
                    "elementId": "n2",
                    "labels": ["Occurrence"],
                    "properties": {"name": "Pump occurrence"},
                    "can_traverse": False,
                },
                "r": {
                    "elementId": "r1",
                    "type": "PartRef",
                    "start": "n1",
                    "end": "n2",
                    "properties": {},
                },
            }
        ]
    )

    assert next(node for node in graph["nodes"] if node["elementId"] == "n1")["can_traverse"] is True
    assert graph["relationships"][0]["type"] == "PART_REFERENCE"
    assert graph["relationships"][0]["properties"]["raw_type"] == "PartRef"


def test_get_traversal_slice_reports_direct_depth(monkeypatch):
    monkeypatch.setattr(
        GraphViewService,
        "_run",
        staticmethod(
            lambda _cypher, _params: [
                {
                    "n": {
                        "elementId": "seed-1",
                        "labels": ["Product"],
                        "properties": {"name": "Seed", "can_traverse": True},
                    },
                    "r": None,
                    "m": None,
                }
            ]
        ),
    )

    graph = GraphViewService.get_traversal_slice(node_id="seed-1", limit=20)

    assert graph["view"] == {"type": "traversal-slice", "node_id": "seed-1", "depth": 1, "root_node_id": "seed-1"}
    assert graph["counts"]["nodes"] == 1


def test_get_traversal_slice_query_uses_top_level_can_traverse(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_traversal_slice(node_id="seed-1", limit=20)

    cypher = captured["cypher"]
    params = captured["params"]

    assert "properties: properties(source_node)," in cypher
    assert "can_traverse:" in cypher
    assert "properties(seed) + {" not in cypher
    assert params["node_id"] == "seed-1"
    assert "Product" in params["instance_node_labels"]
    assert "product" in params["semantic_instance_roles"]


def test_get_traversal_slice_depth_two_uses_two_hop_union(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_traversal_slice(node_id="seed-1", limit=20, depth=2)

    cypher = captured["cypher"]
    params = captured["params"]

    assert "UNION" in cypher
    assert "mid AS source_node" in cypher
    assert "target_node" in cypher
    assert params["depth"] == 2


def test_contextual_subgraph_search_query_matches_element_id_and_property_keys(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_contextual_subgraph(search="003257", limit=25, search_mode="broader")

    cypher = captured["cypher"]
    params = captured["params"]

    assert "MATCH (seed)" in cypher
    assert "toLower(elementId(seed)) CONTAINS search_term" in cypher
    assert "toLower(elementId(seed)) = search_term" in cypher
    assert "properties: properties(seed)," in cypher
    assert "can_traverse:" in cypher
    assert "properties(seed) + {" not in cypher
    assert "any(label IN labels(seed) WHERE toLower(label) CONTAINS search_term)" not in cypher
    assert "toLower(key) CONTAINS search_term" not in cypher
    assert params["search"] == "003257"
    assert params["search_mode"] == "broader"
    assert "Product" in params["instance_node_labels"]


def test_contextual_subgraph_strips_wildcard_markers_from_search(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_contextual_subgraph(search="REQ-*", limit=25, search_mode="broader")

    assert captured["params"]["search"] == "req"
    assert captured["params"]["wildcard_prefix_search"] is True
    assert "properties(seed)['catalogue_id']" in captured["cypher"]
    assert "STARTS WITH search_term" in captured["cypher"]


def test_instance_node_labels_include_requirement_entities():
    assert "Requirement" in GraphViewService.INSTANCE_NODE_LABELS
    assert "RequirementRevision" in GraphViewService.INSTANCE_NODE_LABELS


def test_contextual_subgraph_empty_search_returns_empty_graph():
    graph = GraphViewService.get_contextual_subgraph(search="", limit=25, search_mode="broader", expand_neighbors=True)

    assert graph["nodes"] == []
    assert graph["relationships"] == []
    assert graph["counts"] == {"nodes": 0, "relationships": 0}
    assert graph["view"]["type"] == "contextual-subgraph"


def test_contextual_subgraph_expand_neighbors_uses_single_root_limit(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_contextual_subgraph(search="003257", limit=25, search_mode="broader", expand_neighbors=True)

    cypher = captured["cypher"]
    assert "WHEN $expand_neighbors THEN 1" in cypher


def test_contextual_subgraph_expand_neighbors_accepts_instance_neighbors_only(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_contextual_subgraph(search="003257", limit=25, search_mode="broader", expand_neighbors=True)

    cypher = captured["cypher"]
    assert "adjacent:Individual" not in cypher
    assert "instance_node_labels" in cypher
    assert "NOT any(label IN labels(candidate) WHERE label IN $schema_node_labels)" in cypher


def test_contextual_subgraph_query_projects_bridge_relationships_without_relationship_functions(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_contextual_subgraph(
        search="part",
        limit=25,
        search_mode="broader",
        expand_neighbors=True,
    )

    cypher = captured["cypher"]
    assert "NULL AS r,\n          bridge_adjacent AS adjacent" in cypher
    assert "AS r_payload" in cypher
    assert "WHEN r_payload IS NOT NULL THEN r_payload" in cypher
    assert "WITH seed, r, adjacent, r_payload" in cypher


def test_contextual_subgraph_keeps_relevance_seed_as_root_after_node_sorting(monkeypatch):
    monkeypatch.setattr(
        GraphViewService,
        "_run",
        staticmethod(
            lambda _cypher, _params: [
                {
                    "n": {
                        "elementId": "seed-z",
                        "labels": ["Product"],
                        "properties": {"name": "Z selected"},
                        "can_traverse": True,
                    },
                    "m": {
                        "elementId": "neighbor-a",
                        "labels": ["Occurrence"],
                        "properties": {"name": "A neighbor"},
                        "can_traverse": False,
                    },
                    "r": {
                        "elementId": "r1",
                        "type": "RELATED_TO",
                        "start": "seed-z",
                        "end": "neighbor-a",
                        "properties": {},
                    },
                }
            ]
        ),
    )

    graph = GraphViewService.get_contextual_subgraph(search="selected", expand_neighbors=True)

    assert [node["elementId"] for node in graph["nodes"]] == ["neighbor-a", "seed-z"]
    assert graph["view"]["root_node_id"] == "seed-z"
    assert graph["root"]["elementId"] == "seed-z"
    assert graph["view"]["mode"] == "neighborhood"


def test_contextual_neighbor_query_applies_scope_and_terminal_node_filters(monkeypatch):
    captured = {}

    def fake_run(cypher, params):
        captured["cypher"] = cypher
        captured["params"] = params
        return []

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    GraphViewService.get_contextual_subgraph(
        search="pump",
        ontology_prefix="ap242",
        import_id="job-1",
        expand_neighbors=True,
    )

    assert "direct_adjacent.import_id = $import_id" in captured["cypher"]
    assert "direct_adjacent.ontology_prefix = $ontology_prefix" in captured["cypher"]
    assert "label IN $schema_node_labels" in captured["cypher"]
    assert captured["params"]["import_id"] == "job-1"
