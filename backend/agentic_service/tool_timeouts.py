"""Bound HTTP tool waits according to the downstream operation."""
from backend.depo_platform.network import bounded_timeout_seconds, ontology_publication_timeout_seconds


def tool_timeout_seconds(tool, inputs):
    normal = bounded_timeout_seconds('AGENTIC_TOOL_TIMEOUT_SECONDS', default=30)
    if tool.get('id') in {'ontology.merge.preview', 'ontology.merge.apply', 'ontology.merge.apply_automatic'}:
        validation = bounded_timeout_seconds('MERGE_VALIDATION_TIMEOUT_SECONDS', default=180, maximum=900)
        publication = ontology_publication_timeout_seconds() if tool.get('id') == 'ontology.merge.apply' and inputs.get('publish') is True else 0
        return max(normal, validation + publication + 30)
    return normal
