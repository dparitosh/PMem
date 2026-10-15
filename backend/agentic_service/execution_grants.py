"""Server credentials for a plan already authorized by its submitting caller."""
import os


def verify_grant(snapshot):
    from fastapi import HTTPException
    from .durable_workflows import credential_snapshot
    from backend.depo_platform.authorization import require_active_token
    from backend.depo_platform.credentials import uses_postgres, verify_key
    if credential_snapshot(snapshot.keys()) != snapshot:
        raise HTTPException(403, 'Workflow service credentials changed; reconcile before restarting')
    for name in snapshot:
        require_active_token(name)
        if uses_postgres():
            verify_key(name, os.environ[name].strip())


def execution_identity(request, payload, steps):
    """Call only after validating the original caller and exact workflow plan."""
    if os.getenv('AUTH_MODE', 'token').lower() != 'token':
        return request, payload.get('approval_token'), None
    from fastapi import HTTPException
    from starlette.requests import Request
    from .durable_workflows import workflow_credentials, credential_snapshot
    required = workflow_credentials(steps)
    snapshot = credential_snapshot(required)
    if set(snapshot) != required:
        raise HTTPException(503, 'Configure workflow service credentials before starting background execution')
    verify_grant(snapshot)
    execution = Request({'type': 'http', 'method': 'POST', 'path': '/api/v1/workflow-runs',
        'headers': [(b'authorization', ('Bearer ' + os.environ['GRAPH_READ_TOKEN'].strip()).encode())],
        'client': ('127.0.0.1', 0)})
    execution.state.request_id = getattr(request.state, 'request_id', '')
    return execution, os.getenv('AGENTIC_APPROVAL_TOKEN', '').strip(), snapshot
