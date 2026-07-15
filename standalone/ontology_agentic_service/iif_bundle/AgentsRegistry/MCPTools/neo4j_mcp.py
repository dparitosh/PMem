"""Neo4j MCP tool factory compatible with the IIF runtime registry."""

from __future__ import annotations

import json
import os
import re


_WRITE_TOKENS = {"create", "delete", "detach", "drop", "merge", "remove", "set", "update", "write"}


def _tool_name(tool) -> str:
    metadata = getattr(tool, "metadata", None)
    return str(getattr(metadata, "name", "") or getattr(tool, "name", "")).strip()


def _write_like(name: str) -> bool:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    tokens = {token for token in re.split(r"[^a-z0-9]+", snake_case.lower()) if token}
    return bool(tokens & _WRITE_TOKENS)


def _filter_tools(tools):
    if os.getenv("NEO4J_MCP_SECURITY_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return tools
    allowed = {
        value.strip()
        for value in os.getenv("NEO4J_MCP_ALLOWED_TOOLS", "").split(",")
        if value.strip()
    }
    allow_writes = os.getenv("NEO4J_MCP_ALLOW_WRITES", "false").strip().lower() in {"1", "true", "yes", "on"}
    filtered = []
    for tool in tools:
        name = _tool_name(tool)
        if allowed and name not in allowed:
            continue
        if not allow_writes and _write_like(name):
            continue
        filtered.append(tool)
    return filtered


async def get_neo4j_mcp_tools():
    """Discover Neo4j tools from the configured MCP server.

    Configuration is external so credentials never appear in agent YAML files.
    The factory returns an empty list when MCP is disabled or unreachable,
    allowing non-Neo4j ontology workflows to keep loading.
    """
    if os.getenv("NEO4J_MCP_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return []
    try:
        from llama_index.tools.mcp import BasicMCPClient, McpToolSpec

        command_or_url = os.getenv("NEO4J_MCP_URL", "http://127.0.0.1:8080/mcp").strip()
        args = json.loads(os.getenv("NEO4J_MCP_ARGS", "[]"))
        env = json.loads(os.getenv("NEO4J_MCP_ENV_JSON", "{}"))
        client = BasicMCPClient(command_or_url=command_or_url, args=args, env=env)
        tools = await McpToolSpec(client=client).to_tool_list_async()
        return _filter_tools(tools)
    except Exception:
        return []


__all__ = ["get_neo4j_mcp_tools"]
