from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter(prefix="/graph", tags=["semantic-bridge"])

def bridge_service_identity(request: Request):
    """Private service credential, never forwarded to browser clients."""
    import os, hmac
    expected = os.getenv('GRAPH_PUBLICATION_TOKEN', '')
    supplied = request.headers.get('authorization', '')
    if not expected or not hmac.compare_digest(supplied, 'Bearer ' + expected):
        raise HTTPException(403, 'Graph service publication credential required')


@router.post('/bridge/publications', dependencies=[Depends(bridge_service_identity)])
def publish_bridge(payload: dict):
    from .bridge_publication import publish
    try:
        return publish(payload)
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, 'Publication validation failed; review the saved preview and graph state.') from exc


@router.get('/bridge/publications/{publication_id}', dependencies=[Depends(bridge_service_identity)])
def bridge_receipt(publication_id: str):
    from .bridge_publication import receipt
    result = receipt(publication_id)
    if result is None:
        raise HTTPException(404, 'Publication receipt not found')
    return result
