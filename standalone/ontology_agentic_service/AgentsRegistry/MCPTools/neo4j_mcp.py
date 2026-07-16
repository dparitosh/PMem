"""Optional Neo4j MCP tool factory for IIF."""

import json
import os
import re
from typing import Any


_WRITE_TOKENS = {"create", "delete", "detach", "drop", "merge", "remove", "set", "update", "write"}


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _json_env(name: str, default: Any) -> Any:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must contain valid JSON") from exc


def _tokens(name: str) -> set[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return {part.lower() for part in re.split(r"[^A-Za-z0-9]+", separated) if part}


def _tool_name(tool: Any) -> str:
    metadata = getattr(tool, "metadata", None)
    return str(getattr(metadata, "name", "") or getattr(tool, "name", ""))


async def get_neo4j_mcp_tools() -> list[Any]:
    """Return configured Neo4j MCP tools, or no tools when the connector is disabled."""
    if not _enabled("NEO4J_MCP_ENABLED"):
        return []
    try:
        from llama_index.tools.mcp import BasicMCPClient, McpToolSpec
    except ImportError as exc:
        raise RuntimeError("Install llama-index-tools-mcp to enable Neo4j MCP") from exc

    target = os.getenv("NEO4J_MCP_URL", "").strip() or os.getenv("NEO4J_MCP_COMMAND", "").strip()
    if not target:
        raise ValueError("Set NEO4J_MCP_URL or NEO4J_MCP_COMMAND when Neo4j MCP is enabled")
    args = _json_env("NEO4J_MCP_ARGS_JSON", [])
    env = _json_env("NEO4J_MCP_ENV_JSON", {})
    if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
        raise ValueError("NEO4J_MCP_ARGS_JSON must be a JSON array of strings")
    if not isinstance(env, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items()):
        raise ValueError("NEO4J_MCP_ENV_JSON must be a JSON object of string values")

    client = BasicMCPClient(command_or_url=target, args=args, env=env)
    tools = list(await McpToolSpec(client=client).to_tool_list_async())
    if not _enabled("NEO4J_MCP_SECURITY_ENABLED"):
        return tools

    allowed = {value.strip() for value in os.getenv("NEO4J_MCP_ALLOWED_TOOLS", "").split(",") if value.strip()}
    allow_writes = _enabled("NEO4J_MCP_ALLOW_WRITES")
    filtered = []
    for tool in tools:
        name = _tool_name(tool)
        if allowed and name not in allowed:
            continue
        if not allow_writes and _tokens(name) & _WRITE_TOKENS:
            continue
        filtered.append(tool)
    return filtered


__all__ = ["get_neo4j_mcp_tools"]
