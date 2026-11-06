"""One publication dispatch; response loss is reconciled by identity, never replayed."""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import httpx
from .network import graph_dispatch_timeout_seconds, service_bearer_headers
from .peer_http import async_peer_response
from .operations import OperationContext, operation_scope


class PublicationUnverified(RuntimeError):
    def __init__(self, ontology_id, publication_id, receipt_url):
        self.ontology_id, self.publication_id, self.receipt_url = ontology_id, publication_id, receipt_url
        super().__init__(f'Publication outcome is unverified; verify receipt {publication_id} before any retry')


def verified_receipt(payload, ontology_id, publication_id):
    return (isinstance(payload, dict) and payload.get('ontology_id') == ontology_id
            and payload.get('publication_id') == publication_id
            and (payload.get('status') == 'success' or
                 payload.get('status') == 'published' and payload.get('current') is True)
            and all(type(payload.get(key)) is int and payload[key] >= 0
                    for key in ('resources', 'relationships', 'hierarchy_edges')))


def receipt_endpoint(base, ontology_id, publication_id):
    return f"{base.rstrip('/')}/graph/ontologies/{quote(ontology_id, safe='')}/publications/{quote(publication_id, safe='')}"


async def verify_publication(base, ontology_id, publication_id):
    endpoint = receipt_endpoint(base, ontology_id, publication_id)
    # A bounded read-only reconciliation allowance is separate from an expired
    # write budget. It cannot dispatch publication or authorize a new mutation.
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()
    try:
        with operation_scope(OperationContext('publication-receipt', deadline)):
            response = await async_peer_response('GET', endpoint, budget=5,
                headers=service_bearer_headers('GRAPH_READ_TOKEN', service_name='graph publication receipt', endpoint=endpoint))
        if response.status_code == 200:
            payload = response.json()
            if verified_receipt(payload, ontology_id, publication_id):
                return {**payload, 'status':'success', 'reconciled':True}
    except (httpx.HTTPError, TimeoutError, ValueError, RuntimeError):
        pass
    raise PublicationUnverified(ontology_id, publication_id, endpoint)


async def publish_graph(base, *, content, ontology_id, prefix, publication_id=None):
    publication_id = publication_id or hashlib.sha256(content).hexdigest()
    endpoint = base.rstrip('/') + '/graph/ontologies/publish'
    headers = service_bearer_headers('GRAPH_PUBLICATION_TOKEN', service_name='graph publication API', endpoint=endpoint)
    try:
        response = await async_peer_response('POST', endpoint, budget=graph_dispatch_timeout_seconds(), headers=headers,
            data={'ontology_id':ontology_id, 'prefix':prefix, 'publication_id':publication_id},
            files={'artifact':(f'{ontology_id}.ttl', content, 'text/turtle')})
    except (httpx.TransportError, TimeoutError, asyncio.CancelledError):
        # Cancellation cannot recall a dispatched commit. Only a bounded,
        # read-only receipt lookup is permitted after losing its response.
        return await verify_publication(base, ontology_id, publication_id)
    if response.status_code >= 500 or response.status_code == 409:
        return await verify_publication(base, ontology_id, publication_id)
    response.raise_for_status()  # Known input/authentication rejection is not response loss.
    try:
        payload = response.json()
    except ValueError:
        return await verify_publication(base, ontology_id, publication_id)
    if not verified_receipt(payload, ontology_id, publication_id):
        return await verify_publication(base, ontology_id, publication_id)
    return payload
