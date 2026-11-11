"""Bound HTTP tool waits according to the downstream operation."""
from backend.depo_platform.network import bounded_timeout_seconds, ontology_publication_timeout_seconds, engineering_workflow_timeout_seconds


def tool_timeout_seconds(tool, inputs):
    normal = bounded_timeout_seconds('AGENTIC_TOOL_TIMEOUT_SECONDS', default=30)
    if tool.get('id') == 'ontology.consistency.check':
        normal = max(normal,bounded_timeout_seconds('DEPO_REASONER_TIMEOUT_SECONDS',default=60,maximum=180)+30)
    if tool.get('id') == 'engineering.publish':
        normal = max(normal, engineering_workflow_timeout_seconds() + 30)
    if tool.get('id') == 'bridge.mapping.preview':
        normal = max(normal,bounded_timeout_seconds('BRIDGE_SOURCE_TIMEOUT_SECONDS',default=300,maximum=900)+30)
    if tool.get('id') in {'ontology.merge.preview', 'ontology.merge.apply', 'ontology.merge.apply_automatic'}:
        validation = bounded_timeout_seconds('MERGE_VALIDATION_TIMEOUT_SECONDS', default=180, maximum=900)
        publication = ontology_publication_timeout_seconds() if tool.get('id') == 'ontology.merge.apply' and inputs.get('publish') is True else 0
        normal = max(normal, validation + publication + 30)
    from backend.depo_platform.operations import current_operation
    operation = current_operation()
    return operation.timeout(normal) if operation else normal
