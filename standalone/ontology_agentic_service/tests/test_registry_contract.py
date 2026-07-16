import importlib
import inspect
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AgentsRegistry" / "Agents"


EXPECTED = {
    "Ontology Intake Agent": {"ontology_inspect", "owlready2_analyze", "external_registered_ontologies"},
    "Ontology Review Agent": {"ontology_review", "owlready2_analyze"},
    "Ontology Alignment Agent": {"ontology_alignment_plan", "external_context_graph_search", "neo4j_mcp"},
    "Ontology Export Agent": {"ontology_export"},
}


def test_agent_tool_mapping_is_complete_and_canvas_composable():
    loaded = {}
    for path in sorted(AGENTS.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        loaded[data["name"]] = {tool["name"] for tool in data["tools"]}
        assert data["can_handoff_to"] == []
        assert "system_prompt:" not in data["system_prompt"]
        assert "\ntools:" not in data["system_prompt"]
        for tool in data["tools"]:
            assert tool["type"] in {"python", "mcp"}
            assert tool["module"].startswith("AgentsRegistry.")
            assert tool["object"]
    assert loaded == EXPECTED


def test_external_and_mcp_boundaries_are_not_mixed():
    for path in AGENTS.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for tool in data["tools"]:
            if tool["name"].startswith("external_"):
                assert tool["module"].endswith("ontology_external_api_tools")
                assert tool["type"] == "python"
            if tool["name"] == "neo4j_mcp":
                assert tool["module"].endswith("neo4j_mcp")
                assert tool["type"] == "mcp"


def test_every_yaml_tool_resolves_to_the_declared_object():
    for path in AGENTS.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for tool in data["tools"]:
            module = importlib.import_module(tool["module"])
            declared = getattr(module, tool["object"])
            if tool["type"] == "mcp":
                assert inspect.iscoroutinefunction(declared)
            else:
                assert declared is not None


def test_old_service_layout_is_absent():
    assert not (ROOT / "app").exists()
    assert not (ROOT / "ontology_agentic").exists()
    assert not (ROOT / "iif_bundle").exists()
    assert not (ROOT / "start_service.py").exists()


def test_tool_modules_compile_when_iif_prepends_generated_content():
    tool_files = list((ROOT / "AgentsRegistry" / "CodedTools").glob("*.py"))
    tool_files += list((ROOT / "AgentsRegistry" / "MCPTools").glob("*.py"))
    for path in tool_files:
        source = path.read_text(encoding="utf-8")
        assert "from __future__ import" not in source
        compile("IIF_GENERATED_HEADER = True\n" + source, str(path), "exec")
