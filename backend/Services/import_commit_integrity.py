"""Import background-write deadlines and completeness checks."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from backend.depo_platform.operations import OperationContext, current_operation, operation_scope
from backend.depo_platform.network import bounded_timeout_seconds
from backend.depo_platform.execution_guard import has_execution_guard

@contextmanager
def commit_operation(task_id):
    # A leased parent remains authoritative. A direct HTTP request only queues
    # this job; its short transport deadline must not kill later write batches.
    inherited = current_operation()
    if inherited is not None and has_execution_guard():
        yield inherited
        return
    seconds = bounded_timeout_seconds('IMPORT_COMMIT_MAX_SECONDS', default=1800, minimum=60, maximum=3600)
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
    with operation_scope(OperationContext(task_id, deadline)) as context:
        yield context

def require_relationship_batch(result, expected, relationship_type):
    if result.get('errors'):
        raise RuntimeError(f'Relationship write failed for {relationship_type}; partial graph may exist. Inspect retained errors before retrying: {result["errors"][0]}')
    matched = result.get('matched_rows')
    if type(matched) is not int or matched != expected:
        raise RuntimeError(f'Relationship completeness failed for {relationship_type}: matched {matched!r} of {expected} references. Partial graph may exist; retry requires reconciliation.')
    return matched


def scoped_merge_keys(keys):
    """A new import must never steal nodes from a prior task with the same file."""
    result = list(dict.fromkeys(str(key) for key in keys if key))
    if 'import_id' not in result:
        result.append('import_id')
    return result
