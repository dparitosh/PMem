"""Machine-readable contracts for the five standalone ontology tools."""

from __future__ import annotations

import inspect
from typing import Any

from ontology_agentic import tools


_SIDE_EFFECTS = {
    "ontology_inspect": "read_only",
    "ontology_review": "read_only",
    "ontology_alignment_plan": "read_only",
    "ontology_export": "filesystem_write",
    "owlready2_analyze": "read_only_cpu_intensive",
}


def describe_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "category": "ontology",
            "callable": True,
            "signature": str(inspect.signature(getattr(tools, name))),
            "side_effect": _SIDE_EFFECTS[name],
            "requires_approval": name == "ontology_export",
            "execution_mode": "sync",
        }
        for name in tools.__all__
    ]


def validate_tool_catalog() -> list[str]:
    return [name for name in tools.__all__ if not callable(getattr(tools, name, None))]
