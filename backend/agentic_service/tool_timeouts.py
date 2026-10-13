"""Bound HTTP tool waits according to the downstream operation."""
from backend.depo_platform.network import bounded_timeout_seconds


def tool_timeout_seconds(tool, inputs):
    normal = bounded_timeout_seconds('AGENTIC_TOOL_TIMEOUT_SECONDS', default=30)
    if tool.get('id') == 'ontology.merge.apply' and inputs.get('publish') is True:
        publication = bounded_timeout_seconds('GRAPH_PUBLICATION_TIMEOUT_SECONDS', default=180, maximum=3600)
        return max(normal, publication * 2 + 30)
    return normal
