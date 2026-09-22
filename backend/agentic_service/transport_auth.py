"""Explicit downstream credentials; never forward unverified identity headers."""
import os
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

# These endpoints consume approval fields in their JSON body, not bearer tokens.
APPROVAL_TOKENS = {
    'ontology.transition': 'ONTOLOGY_APPROVAL_TOKEN',
    'ontology.merge.apply': 'ONTOLOGY_APPROVAL_TOKEN',
    'data.product.publish': 'DATA_PRODUCT_APPROVAL_TOKEN',
    'pipeline.run': 'DATA_JOB_EXECUTION_TOKEN',
    'pipeline.transform': 'DATA_JOB_EXECUTION_TOKEN',
}


def downstream_headers(request: Request, endpoint: str, *, graph_read=False) -> dict:
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
        return {'Authorization': bearer}
    if mode == 'token' and graph_read:
        token = os.getenv('GRAPH_READ_TOKEN', '').strip()
        if not token:
            raise HTTPException(503, 'GRAPH_READ_TOKEN is required for downstream reads')
        return {'Authorization': 'Bearer ' + token}
    return {}


def downstream_inputs(tool: dict, inputs: dict, actor: str | None) -> dict:
    result = {key: value for key, value in inputs.items() if key not in {'approval_token', 'approved_by'}}
    key = APPROVAL_TOKENS.get(tool['id'])
    if key:
        if not actor:
            raise HTTPException(403, 'Approval is required before dispatch')
        result['approved_by'] = actor
        if os.getenv('AUTH_MODE', 'token').lower() == 'token':
            token = os.getenv(key, '').strip()
            if not token:
                raise HTTPException(503, f'{key} is required for this tool')
            result['approval_token'] = token
    return result
