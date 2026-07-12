import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from ontology_agentic.tool_catalog import describe_tools, validate_tool_catalog


def test_tool_catalog_exports_callable_contracts() -> None:
    tools = describe_tools()
    assert len(tools) == 27
    assert validate_tool_catalog() == []
    assert all(item["signature"] for item in tools)


def test_mutating_tools_are_marked_for_approval() -> None:
    tools = {item["name"]: item for item in describe_tools()}
    assert tools["depo_merge_ontologies"]["requires_approval"] is True
    assert tools["depo_execute_semantic_workflow"]["requires_approval"] is True
    assert tools["inspect_ontology_artifact"]["side_effect"] == "read_only"
