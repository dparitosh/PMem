import asyncio

from AgentsRegistry.MCPTools import neo4j_mcp


def test_neo4j_mcp_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NEO4J_MCP_ENABLED", raising=False)
    assert asyncio.run(neo4j_mcp.get_neo4j_mcp_tools()) == []


def test_write_detection_uses_name_tokens_not_substrings():
    assert neo4j_mcp._tokens("create_node") & neo4j_mcp._WRITE_TOKENS
    assert neo4j_mcp._tokens("getDataset") & neo4j_mcp._WRITE_TOKENS == set()
    assert neo4j_mcp._tokens("mergeRelationship") & neo4j_mcp._WRITE_TOKENS
