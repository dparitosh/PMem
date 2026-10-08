"""Explicit downstream credentials; never forward unverified identity headers."""
import os
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

# Human approval contracts; service boundary headers are handled separately.
APPROVAL_TOKENS = {
    'bridge.mapping.preview': 'AGENTIC_APPROVAL_TOKEN',
    'bridge.mapping.publish': 'AGENTIC_APPROVAL_TOKEN',
    'ontology.register': 'ONTOLOGY_APPROVAL_TOKEN',
    'ontology.transition': 'ONTOLOGY_APPROVAL_TOKEN',
    'ontology.merge.apply': 'ONTOLOGY_APPROVAL_TOKEN',
    'data.product.publish': 'DATA_PRODUCT_APPROVAL_TOKEN',
    'data.product.revoke': 'DATA_PRODUCT_APPROVAL_TOKEN',
    'pipeline.run': 'DATA_JOB_EXECUTION_TOKEN',
    'pipeline.transform': 'DATA_JOB_EXECUTION_TOKEN',
    'engineering.publish': 'AGENTIC_APPROVAL_TOKEN',
    'oslc.remote.sync': 'AGENTIC_APPROVAL_TOKEN',
    'qif.task.commit': 'AGENTIC_APPROVAL_TOKEN',
    'context.upsert': 'AGENTIC_APPROVAL_TOKEN',
}


def tool_retry_allowed(tool: dict, *, attempt: int, retries: int, status_code: int) -> bool:
    """Only explicitly non-mutating tools may retry an uncertain failure."""
    return attempt <= retries and status_code >= 500 and tool.get('mutates') is False


def downstream_headers(request: Request, endpoint: str, *, graph_read=False, tool: dict | None = None) -> dict:
    from backend.depo_platform.network import gateway_subscription_headers
    gateway_headers = gateway_subscription_headers(endpoint)
    mode = os.getenv('AUTH_MODE', 'token').lower()
    if mode == 'entra':
        # The caller has already passed gateway/role validation. Forward its JWT
        # through a configured HTTPS gateway, which revalidates it and creates
        # fresh identity headers. Never copy X-DEPO-* or X-MS-* from the caller.
        url = urlsplit(endpoint)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise HTTPException(503, 'Entra downstream endpoints must use an HTTPS API gateway')
        bearer = request.headers.get('authorization', '')
        if not bearer.lower().startswith('bearer ') or not bearer[7:].strip():
            raise HTTPException(503, 'The gateway must preserve the caller bearer token for downstream authorization')
        return {**gateway_headers, 'Authorization': bearer}
    if mode == 'token':
        if graph_read:
            # Caller has already passed graph_read_identity. Preserve its
            # current credential across database-backed key rotation.
            bearer = request.headers.get('authorization', '').strip()
            if bearer.lower().startswith('bearer ') and bearer[7:].strip():
                return {**gateway_headers, 'Authorization': bearer}
            key = request.headers.get('x-api-key', '').strip()
            if key:
                return {**gateway_headers, 'Authorization': 'Bearer ' + key}
            raise HTTPException(403, 'Verified graph read credential is required')
        token_key = 'GRAPH_READ_TOKEN' if graph_read else None
        if tool:
            service = tool.get('service')
            method = str(tool.get('method', 'GET')).upper()
            if method not in {'GET', 'HEAD', 'OPTIONS'} and service in {'ontology', 'qif', 'ingestion'}:
                token_key = 'INGESTION_WRITE_TOKEN' if service == 'ingestion' else 'ONTOLOGY_APPROVAL_TOKEN'
            else:
                # Protected read/evidence APIs span several services. A read
                # credential also accompanies body-authorized mutations; it
                # never substitutes for their approval token.
                token_key = 'GRAPH_READ_TOKEN'
        if not token_key:
            return {}
        token = os.getenv(token_key, '').strip()
        from backend.depo_platform.authorization import require_active_token
        require_active_token(token_key)
        if not token:
            raise HTTPException(503, f'{token_key} is required for downstream authorization')
        return {**gateway_headers, 'Authorization': 'Bearer ' + token}
    return {}


def downstream_inputs(tool: dict, inputs: dict, actor: str | None) -> dict:
    result = {key: value for key, value in inputs.items() if key not in {'approval_token', 'approved_by'}}
    key = APPROVAL_TOKENS.get(tool['id'])
    if tool.get('mutates') and not key:
        raise HTTPException(503, f"Mutating tool {tool['id']} has no downstream approval contract")
    if key:
        if not actor:
            raise HTTPException(403, 'Approval is required before dispatch')
        result['approved_by'] = actor
        if os.getenv('AUTH_MODE', 'token').lower() == 'token':
            token = os.getenv(key, '').strip()
            from backend.depo_platform.authorization import require_active_token
            require_active_token(key)
            if not token:
                raise HTTPException(503, f'{key} is required for this tool')
            result['approval_token'] = token
    return result
