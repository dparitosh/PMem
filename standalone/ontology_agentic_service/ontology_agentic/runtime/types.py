from dataclasses import dataclass, field
from typing import Any, Callable


AgentHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class AgentSpec:
    name: str
    description: str
    use_case: str
    role: str
    objective: list[str]
    input_context: list[str]
    checks: list[str]
    constraints: list[str]
    output_rules: list[str]
    output_schema: dict[str, Any]
    termination_rule: str
    additional_guidelines: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class RegisteredAgent:
    spec: AgentSpec
    handler_name: str
    handler: AgentHandler
