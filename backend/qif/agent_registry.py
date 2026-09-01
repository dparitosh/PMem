"""Lightweight registry for declarative QIF agents.

This mirrors the YAML-discovered service pattern used by the PDF Intelligence
reference without making QIF ingestion dependent on an LLM runtime.
"""
import importlib
from pathlib import Path
from typing import Any

import yaml


class QifAgentRegistry:
    def __init__(self) -> None:
        self._agent_dir = Path(__file__).parent / "agents"

    def list_agents(self) -> list[dict[str, Any]]:
        agents: list[dict[str, Any]] = []
        for path in sorted(self._agent_dir.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            agents.append({
                "name": raw.get("name", path.stem),
                "description": raw.get("description", ""),
                "tools": [tool.get("name", tool.get("object", "")) for tool in raw.get("tools", [])],
            })
        return agents

    def resolve_tools(self, agent_name: str) -> dict[str, Any]:
        """Resolve the declarative tool list for a rule-driven QIF agent run."""
        for path in sorted(self._agent_dir.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if raw.get("name") != agent_name:
                continue
            resolved = {}
            for ref in raw.get("tools", []):
                module = importlib.import_module(ref["module"])
                resolved[ref.get("name") or ref["object"]] = getattr(module, ref["object"])
            return resolved
        raise KeyError(f"QIF agent '{agent_name}' is not registered")


registry = QifAgentRegistry()
