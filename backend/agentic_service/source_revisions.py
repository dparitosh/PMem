"""Read authoritative ontology revision receipts through the owning API."""
import re
import asyncio
from urllib.parse import quote
from backend.depo_platform.network import bounded_timeout_seconds

from .companion_context import _read_json


def ontology_ids(scope):
    identifiers = {scope[key] for key in ('ontology_id', 'source_ontology_id', 'target_ontology_id',
                   'qif_ontology_id', 'ap242_ontology_id') if scope.get(key)}
    identifiers.update(scope.get('source_ontology_ids') or [])
    if len(identifiers) > 10:
        raise ValueError('Too many ontology revisions')
    return sorted(identifiers)


async def capture(scope, headers):
    budget = bounded_timeout_seconds('COMPANION_RETRIEVAL_TIMEOUT_SECONDS', default=15, maximum=120)
    async with asyncio.timeout(budget):
        return await _capture(scope, headers)


async def _capture(scope, headers):
    receipts = []
    for identifier in ontology_ids(scope):
        body, _ = await _read_json('ONTOLOGY_SERVICE_URL', 'http://127.0.0.1:8011',
            '/ontologies/' + quote(identifier, safe='') + '/revision', {}, headers)
        if (body.get('ontology_id') != identifier or
                not re.fullmatch(r'[0-9a-f]{64}', str(body.get('artifact_sha256', '')))):
            raise ValueError('Invalid ontology revision receipt')
        if body.get('status') == 'superseded' or body.get('lifecycle_status') in {'deprecated', 'retired'}:
            raise ValueError('Selected ontology is no longer current')
        receipts.append({key: body.get(key) for key in
            ('ontology_id', 'artifact_sha256', 'lifecycle_status', 'status')})
    return receipts


async def verify(record, headers):
    expected = record.get('source_revisions')
    if expected is None:
        return False  # Existing runs retain their previous source checks.
    current = await capture(record.get('scope') or {}, headers)
    if current != expected:
        raise ValueError('Selected ontology revision or lifecycle changed; start a new review')
    return True
