import importlib
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "iif_bundle"
pytestmark = pytest.mark.filterwarnings("ignore:The 'validate_default' attribute.*:UserWarning")


def test_bundle_agent_tool_and_workflow_contracts() -> None:
    agent_files = sorted((BUNDLE / "AgentsRegistry" / "Agents").glob("*.yaml"))
    agents = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in agent_files]
    assert {agent["name"] for agent in agents} == {
        "ontology_intake_agent",
        "ontology_review_agent",
        "ontology_alignment_agent",
        "ontology_export_agent",
    }
    assert all(agent.get("can_handoff_to") == [] for agent in agents)

    expected_tools = {
        "ontology_inspect_api",
        "ontology_review_api",
        "ontology_alignment_api",
        "ontology_export_api",
        "owlready2_reasoning_api",
        "neo4j_mcp",
    }
    referenced_tools = {tool["name"] for agent in agents for tool in agent.get("tools", [])}
    assert referenced_tools == expected_tools
    assert {
        tool["module"] for agent in agents for tool in agent.get("tools", [])
    } == {
        "AgentsRegistry.CodedTools.ontology_workflow_tools",
        "AgentsRegistry.MCPTools.neo4j_mcp",
    }

    guide = (BUNDLE / "HOW_TO_BUILD_AND_TEST_WORKFLOWS.txt").read_text(encoding="utf-8")
    assert "DRAG AND DROP WORKFLOW CREATION" in guide
    assert "COMPLETE AGENT-TO-TOOL MAPPING" in guide
    assert "TEST IN IIF" in guide
    assert not (BUNDLE / "storage").exists()


def test_bundle_adapter_calls_external_ontology_api(monkeypatch) -> None:
    sys.path.insert(0, str(BUNDLE))
    try:
        adapter = importlib.import_module("AgentsRegistry.CodedTools.ontology_workflow_tools")
        calls = {}

        def fake_post(endpoint, payload, base_url, timeout_seconds):
            calls.update(endpoint=endpoint, payload=payload, base_url=base_url, timeout=timeout_seconds)
            return {"result": {"classes": 1}}

        monkeypatch.setattr(adapter, "_post_json", fake_post)
        result = adapter.ontology_inspect_api("D:/data/source.owl", base_url="http://ontology-api:8012")
        assert result["classes"] == 1
        assert calls["endpoint"] == "/api/v1/agents/ontology_intake_agent/run"
        assert calls["payload"]["inputs"]["ontology_path"] == "D:/data/source.owl"
        assert adapter.ontology_inspect_api_tool.metadata.name == "ontology_inspect_api"
    finally:
        sys.path.remove(str(BUNDLE))


def test_neo4j_mcp_factory_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("NEO4J_MCP_ENABLED", raising=False)
    sys.path.insert(0, str(BUNDLE))
    try:
        module = importlib.import_module("AgentsRegistry.MCPTools.neo4j_mcp")
        import asyncio

        assert asyncio.run(module.get_neo4j_mcp_tools()) == []
    finally:
        sys.path.remove(str(BUNDLE))


def test_secure_adapter_rejects_base_url_override(monkeypatch) -> None:
    sys.path.insert(0, str(BUNDLE))
    try:
        adapter = importlib.import_module("AgentsRegistry.CodedTools.ontology_workflow_tools")
        monkeypatch.setenv("ONTOLOGY_API_SECURITY_ENABLED", "true")
        monkeypatch.setenv("ONTOLOGY_API_BASE_URL", "https://ontology.example")
        monkeypatch.delenv("ONTOLOGY_API_ALLOW_BASE_URL_OVERRIDE", raising=False)
        try:
            adapter._ontology_api_url("http://127.0.0.1:9999")
        except ValueError as exc:
            assert "override is disabled" in str(exc)
        else:
            assert False
    finally:
        sys.path.remove(str(BUNDLE))


def test_optional_neo4j_security_filters_write_tools(monkeypatch) -> None:
    sys.path.insert(0, str(BUNDLE))
    try:
        module = importlib.import_module("AgentsRegistry.MCPTools.neo4j_mcp")

        class Metadata:
            def __init__(self, name):
                self.name = name

        class Tool:
            def __init__(self, name):
                self.metadata = Metadata(name)

        monkeypatch.setenv("NEO4J_MCP_SECURITY_ENABLED", "true")
        monkeypatch.setenv("NEO4J_MCP_ALLOW_WRITES", "false")
        tools = module._filter_tools(
            [Tool("read_neo4j_cypher"), Tool("get_asset"), Tool("create_relationship"), Tool("deleteNode")]
        )
        assert [tool.metadata.name for tool in tools] == ["read_neo4j_cypher", "get_asset"]
    finally:
        sys.path.remove(str(BUNDLE))
