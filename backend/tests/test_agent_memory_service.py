from backend.Services.agent_memory_service import AgentMemoryService


def test_agent_memory_disabled_is_noop(monkeypatch):
    calls = []
    monkeypatch.setenv("AGENT_MEMORY_ENABLED", "false")
    monkeypatch.setattr(AgentMemoryService, "_query", lambda *args, **kwargs: calls.append((args, kwargs)))

    AgentMemoryService.record_chat_turn(
        session_id="s1",
        user_message="hello",
        assistant_response="world",
        graph_context={"nodes": [{"elementId": "4:abc:1", "label": "Part"}]},
    )

    assert calls == []
    assert AgentMemoryService.status()["enabled"] is False


def test_record_chat_turn_writes_messages_and_touched_nodes(monkeypatch):
    calls = []
    monkeypatch.setenv("AGENT_MEMORY_ENABLED", "true")
    monkeypatch.setattr(AgentMemoryService, "ensure_schema", lambda: {"enabled": True, "ensured": True})
    monkeypatch.setattr(AgentMemoryService, "_query", lambda cypher, params=None: calls.append((cypher, params or {})) or [])

    AgentMemoryService.record_chat_turn(
        session_id="s1",
        user_message="impact?",
        assistant_response="REQ-001 touches Part A",
        graph_context={
            "selectedNode": {"elementId": "4:abc:1", "label": "REQ-001"},
            "nodes": [{"elementId": "4:abc:2", "label": "Part A"}],
        },
    )

    assert len(calls) == 1
    params = calls[0][1]
    assert params["session_id"] == "s1"
    assert params["user_message"] == "impact?"
    assert len(params["touched_nodes"]) == 2


def test_record_semantic_bridge_mappings_stores_approved_only(monkeypatch):
    calls = []
    monkeypatch.setenv("AGENT_MEMORY_ENABLED", "true")
    monkeypatch.setattr(AgentMemoryService, "ensure_schema", lambda: {"enabled": True, "ensured": True})
    monkeypatch.setattr(AgentMemoryService, "_query", lambda cypher, params=None: calls.append((cypher, params or {})) or [])

    AgentMemoryService.record_semantic_bridge_mappings(
        ontology_id="ap242",
        import_task_id="import-1",
        task_id="link-task",
        mappings=[
            {"source_term": "PartA", "ontology_term": "Part", "target_ontology_type": "Class", "selected_for_apply": True, "confidence": 0.9},
            {"source_term": "Noise", "ontology_term": "Thing", "target_ontology_type": "Class", "selected_for_apply": False},
        ],
    )

    assert len(calls) == 1
    rows = calls[0][1]["rows"]
    assert len(rows) == 1
    assert rows[0]["source"] == "PartA"
    assert rows[0]["target"] == "Part"


def test_query_uses_agent_memory_database_override(monkeypatch):
    class FakeResult:
        def data(self):
            return [{"ok": 1}]

    class FakeSession:
        def __init__(self):
            self.database = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, _query, _params):
            return FakeResult()

    class FakeDriver:
        def __init__(self):
            self.session_database = None

        def session(self, database=None):
            self.session_database = database
            return FakeSession()

    fake_driver = FakeDriver()
    monkeypatch.setenv("AGENT_MEMORY_ENABLED", "true")
    monkeypatch.setenv("AGENT_MEMORY_NEO4J_DATABASE", "memory")
    monkeypatch.setattr("backend.core.db_config.get_driver", lambda: fake_driver)

    rows = AgentMemoryService._query("RETURN 1 AS ok", {})

    assert rows == [{"ok": 1}]
    assert fake_driver.session_database == "memory"


def test_semantic_bridge_facts_queries_mapping_memory(monkeypatch):
    captured = {}
    monkeypatch.setenv("AGENT_MEMORY_ENABLED", "true")

    def fake_query(cypher, params=None):
        captured["cypher"] = cypher
        captured["params"] = params
        return [{"source": "REQ-001", "target": "Requirement"}]

    monkeypatch.setattr(AgentMemoryService, "_query", fake_query)

    rows = AgentMemoryService.semantic_bridge_facts("mbse", limit=25)

    assert rows == [{"source": "REQ-001", "target": "Requirement"}]
    assert captured["params"]["ontology_id"] == "mbse"
    assert captured["params"]["limit"] == 25


def test_ensure_schema_is_attempted_once(monkeypatch):
    calls = []
    monkeypatch.setenv("AGENT_MEMORY_ENABLED", "true")
    monkeypatch.setattr(AgentMemoryService, "_schema_attempted", False)
    monkeypatch.setattr(AgentMemoryService, "_query", lambda cypher, params=None: calls.append(cypher) or [])

    first = AgentMemoryService.ensure_schema()
    second = AgentMemoryService.ensure_schema()

    assert first["ensured"] is True
    assert second["cached"] is True
    assert len(calls) == 6
