from dataclasses import dataclass, field
from typing import Any, Callable


AgentHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class AgentSpec:
    name: str
    description: str
    system_prompt: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    can_handoff_to: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RegisteredAgent:
    spec: AgentSpec
    handler_name: str
    handler: AgentHandler
