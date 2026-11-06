"""Compatibility contract for the external DT Requirements Design agents.

This is deliberately a read-only adapter: it does not copy code, import a
foreign agent runtime, or grant direct database access. It tells an external
orchestrator which PMem OSLC and agentic capabilities are available.
"""
from __future__ import annotations

from typing import Any


AGENT_CAPABILITY_MAP = {
    "dt_requirements_intelligence": ["engineering.inspect", "oslc.graph_rag"],
    "dt_quality_director": ["pipeline.telemetry", "ceim.contract"],
    "ontology_app_intake": ["oslc.remote.catalog", "oslc.remote.query"],
    "ontology_app_structure_review": ["oslc.remote.query"],
    "ontology_app_semantic_bridge_planner": ["oslc.remote.query", "ceim.contract"],
    "ontology_app_orchestrator": ["oslc.remote.catalog", "oslc.remote.query", "oslc.graph_rag"],
}


def _key(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", "_").split())


def assess_manifest(manifest: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic compatibility report for a DT workflow manifest."""
    manifest = manifest if isinstance(manifest, dict) else {}
    available = {str(item.get("id")) for item in catalog.get("tools", []) if item.get("id")}
    available_agents = {str(item.get("id")) for item in catalog.get("agents", []) if item.get("id")}
    sequence = manifest.get("steps") if "steps" in manifest else manifest.get("sequence")
    errors = []
    if not isinstance(sequence, list):
        errors.append("Workflow steps/sequence must be an array")
    sequence = sequence if isinstance(sequence, list) else []
    mappings = []
    missing = []
    for index, step in enumerate(sequence):
        if not isinstance(step, dict) or not isinstance(step.get("agent"), str) or not step["agent"].strip():
            errors.append(f"Workflow stage {index + 1} requires an agent name")
            continue
        agent_name = str(step["agent"])
        known = _key(agent_name) in AGENT_CAPABILITY_MAP
        required = AGENT_CAPABILITY_MAP.get(_key(agent_name), [])
        unresolved = [tool_id for tool_id in required if tool_id not in available]
        mappings.append({
            "external_agent": agent_name,
            "pmem_agent": _key(agent_name) if _key(agent_name) in available_agents else None,
            "required_tools": required,
            "available_tools": [tool_id for tool_id in required if tool_id in available],
            "missing_tools": unresolved,
            "status": "unmapped" if not known else ("compatible" if not unresolved else "missing_capability"),
        })
        missing.extend(unresolved)
    return {
        "status": "invalid" if errors or not mappings else ("partial" if missing or any(m["status"] == "unmapped" for m in mappings) else "compatible"),
        "validation_errors": errors,
        "execution_verified": False,
        "workflow_id": manifest.get("name") or manifest.get("entry_agent") or "external-workflow",
        "entry_agent": manifest.get("entry_agent"),
        "mappings": mappings,
        "missing_tools": sorted(set(missing)),
        "transport": "OSLC gateway and PMem agentic OpenAPI catalog",
        "write_boundary": "Canonical publication API only; external agents have no direct graph write access",
        "next_action": ("Correct the workflow stages before execution" if errors or not mappings else
                        "Register or map unresolved agents and PMem tools before execution" if missing or any(m["status"] == "unmapped" for m in mappings) else
                        "Configure PMEM_OSLC_GATEWAY_URL for the external pmem_oslc_client"),
    }
