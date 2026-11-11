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
    if tool_id in {'ontology.agent.intake', 'ontology.agent.review', 'ontology.agent.bridge-plan'} and status == 422:
        detail = exc.detail
        if isinstance(cause, httpx.HTTPStatusError):
            try:
                detail = cause.response.json().get('detail')
            except (ValueError, AttributeError):
                detail = None
        if not isinstance(detail, str):
            detail = None
        # Only classify known messages. Never retain arbitrary source paths or request inputs.
        if detail in {'Native ontology artifact is missing or outside its catalog directory',
                      'The selected ontology has no readable source artifact',
                      'ontology_path must name an existing ontology file under an approved ontology data directory'}:
            code, message = 'ontology_review_source_unavailable', 'The selected ontology has no accessible retained RDF/OWL artifact in the agent service. Restore the artifact and verify its approved data directory before rerunning the review.'
        elif detail in {'The selected import task was not found', 'The selected import task retained parsed rows are unavailable'}:
            code, message = 'ontology_review_import_missing', 'The agent service cannot read the selected import task. Refresh imported instances and verify the retained task store is available to that service.'
        elif detail == 'The selected import task has invalid parsed row data':
            code, message = 'ontology_review_import_invalid', 'The selected import has invalid retained row data. Inspect or restore its import artifacts before rerunning the review.'
        elif detail in {'Ontology artifact changed after intake', 'Graph terms changed after intake; review the current graph again'}:
            code, message = 'ontology_review_source_changed', 'The ontology changed during review. Prepare a new review against the current version; do not resume the stale assessment.'
        elif isinstance(detail, str) and detail.startswith(('ontology file exceeds ONTOLOGY_AGENT_MAX_BYTES (', 'Ontology agent input exceeds the configured byte limit')):
            code, message = 'ontology_review_source_too_large', 'The ontology exceeds the agent review byte limit. Review ONTOLOGY_AGENT_MAX_BYTES and available resources before rerunning; no mapping was published by this review.'
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
            elif detail.startswith(('Merge preparation timed out;', 'Merge validation timed out;')) or detail in {
                'Merge source preparation exceeded its deadline', 'Merge preparation exceeded its deadline',
                'Merge validation preparation exceeded its deadline', 'Merge validation result exceeded its deadline',
            }:
                code, message = 'merge_validation_timeout', (
                    'The merge preparation and semantic validation worker exceeded its configured time budget. '
                    'No merge was approved or published. Partition the sources or review '
                    'MERGE_VALIDATION_TIMEOUT_SECONDS with the administrator before retrying.')
    return {'http_status': status, 'error_code': code, 'error_message': message}
