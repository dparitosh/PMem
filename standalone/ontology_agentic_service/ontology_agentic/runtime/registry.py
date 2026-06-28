from pathlib import Path
from typing import Any

import yaml

from ontology_agentic.runtime.types import AgentSpec, RegisteredAgent


class AgentSpecError(RuntimeError):
    """Raised when an agent spec is missing or malformed."""


class AgentRegistry:
    def __init__(self, specs_dir: Path) -> None:
        self.specs_dir = specs_dir
        self._agents: dict[str, RegisteredAgent] = {}

    def register(self, handler_name: str, handler, spec_path: Path) -> None:
        if not spec_path.exists():
            raise AgentSpecError(f"Agent spec not found: {spec_path}")
        payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise AgentSpecError(f"Agent spec must be a mapping: {spec_path}")
        spec = AgentSpec(
            name=payload["name"],
            description=payload["description"],
            use_case=payload.get("use_case", ""),
            role=payload.get("role", ""),
            objective=payload.get("objective", []),
            input_context=payload.get("input_context", []),
            checks=payload.get("what_to_check_or_do", payload.get("checks", [])),
            constraints=payload.get("constraints", []),
            output_rules=payload.get("output_rules", []),
            output_schema=payload.get("output_schema", {}),
            termination_rule=payload.get("termination_rule", ""),
            additional_guidelines=payload.get("additional_guidelines", []),
            tools=payload.get("tools_information", payload.get("tools", [])),
            examples=payload.get("one_shot_examples", payload.get("examples", [])),
        )
        self._agents[spec.name] = RegisteredAgent(
            spec=spec,
            handler_name=handler_name,
            handler=handler,
        )

    def get(self, name: str) -> RegisteredAgent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"Unknown agent: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._agents)

    def describe_all(self) -> list[dict[str, Any]]:
        return [
            {
                "name": agent.spec.name,
                "description": agent.spec.description,
                "use_case": agent.spec.use_case,
                "handler_name": agent.handler_name,
                "tools": agent.spec.tools,
                "checks": agent.spec.checks,
            }
            for agent in self._agents.values()
        ]
