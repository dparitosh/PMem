"""Machine-readable contracts for low-code/no-code tool registration.

The tools remain ordinary Python functions. This catalog supplies the metadata
an external orchestrator needs to expose them as nodes without importing the
FastAPI adapter or guessing whether a tool can mutate data.
"""

from __future__ import annotations

import inspect
from typing import Any

from ontology_agentic import tools


_READ_ONLY = {
    name for name in tools.__all__
    if name.startswith(("inspect_", "review_", "plan_", "normalize_", "requirement_alignment_profile", "depo_healthcheck", "depo_list_", "depo_graph_search", "depo_oslc_"))
}
_APPROVAL_REQUIRED = {"depo_execute_semantic_workflow", "depo_merge_ontologies"}
_FILE_WRITES = {
    name for name in tools.__all__
    if name.startswith(("export_", "depo_export_"))
}


def _category(name: str) -> str:
    if name.startswith("depo_oslc_"):
        return "oslc"
    if name.startswith("depo_"):
        return "depo_api"
    if name.startswith("inspect_step") or name.startswith("export_step"):
        return "cad_step"
    if name.startswith("inspect_reqif") or name.startswith("export_reqif"):
        return "reqif"
    if "requirement" in name:
        return "requirements"
    return "ontology"


def describe_tools() -> list[dict[str, Any]]:
    """Return stable tool-node metadata for external orchestration canvases."""
    records: list[dict[str, Any]] = []
    for name in sorted(tools.__all__):
        function = getattr(tools, name)
        if not callable(function):
            continue
        if name in _APPROVAL_REQUIRED:
            side_effect = "neo4j_write"
        elif name in _FILE_WRITES:
            side_effect = "filesystem_write"
        elif name in _READ_ONLY:
            side_effect = "read_only"
        else:
            side_effect = "read_only"
        records.append({
            "name": name,
            "category": _category(name),
            "callable": True,
            "signature": str(inspect.signature(function)),
            "side_effect": side_effect,
            "requires_approval": name in _APPROVAL_REQUIRED,
            "execution_mode": "sync",
        })
    return records


def validate_tool_catalog() -> list[str]:
    """Return missing or non-callable exports instead of failing at runtime."""
    return [name for name in tools.__all__ if not callable(getattr(tools, name, None))]
