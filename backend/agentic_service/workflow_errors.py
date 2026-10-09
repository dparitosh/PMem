"""Bounded workflow diagnostics without exposing upstream bodies or secrets."""
from fastapi import HTTPException
import httpx


def workflow_error(exc, tool_id):
    if not isinstance(exc, HTTPException):
        return {'error_code': 'tool_execution_failed', 'error_message': 'Tool execution failed. Inspect service logs using this workflow ID.'}
    status = exc.status_code
    code, message = {
        401: ('credential_rejected', 'Service credentials were rejected. Reconnect access and verify downstream service credentials.'),
        403: ('scope_rejected', 'Required service scope was rejected. Verify registered workflow and ontology credentials.'),
        404: ('route_or_source_missing', 'The service route or selected source was not found. Verify the service version and retained source IDs.'),
        409: ('workflow_conflict', 'The operation conflicts with retained state. Refresh and inspect its outcome before retrying.'),
        422: ('invalid_tool_inputs', 'Tool inputs or source artifacts are invalid. Verify the selected sources and required inputs.'),
        503: ('dependency_unavailable', 'A service or required server credential is unavailable. Check service configuration and logs.'),
    }.get(status, ('downstream_failure', 'A dependent service failed. Inspect service logs using this workflow ID.'))
    cause = exc.__cause__
    if tool_id == 'ontology.merge.preview' and isinstance(cause, httpx.HTTPStatusError) and status == 422:
        try:
            detail = cause.response.json().get('detail')
        except (ValueError, AttributeError):
            detail = None
        # Classify known errors; never copy arbitrary response text, paths or IDs.
        if isinstance(detail, str):
            if detail.startswith(('Ontology file is missing:', 'Ontology not found', 'Unknown ontology', 'Ontology artifact not found', 'Ontology artifact is missing:')):
                code, message = 'merge_source_missing', 'A selected ontology has no readable retained RDF artifact. Restore or re-register its RDF/OWL source before merging.'
            elif detail == 'At least two distinct source_ontology_ids are required':
                code, message = 'merge_sources_not_distinct', 'Select two distinct ontologies before merging.'
            elif detail == 'Merge source exceeds ONTOLOGY_MAX_UPLOAD_BYTES':
                code, message = 'merge_source_too_large', 'A merge source exceeds the configured ontology upload limit.'
    return {'http_status': status, 'error_code': code, 'error_message': message}
