"""Read authoritative ontology revision receipts through the owning API."""
import re
import asyncio
import httpx
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
        try:
            body, _ = await _read_json('ONTOLOGY_SERVICE_URL', 'http://127.0.0.1:8011',
                '/ontologies/' + quote(identifier, safe='') + '/revision', {}, headers)
        except httpx.HTTPStatusError as failure:
            # A legacy source namespace is not a registered ontology artifact.
            # Preserve the revision guard using the owning graph's exact source.
            if failure.response.status_code!=404 or not scope.get('node_id') or identifier!=scope.get('ontology_id'):
                raise
            body,_=await _read_json('GRAPH_SERVICE_URL','http://127.0.0.1:8013','/graph/source-revision',
                {'node_id':scope['node_id'],'ontology_id':identifier},headers)
            if (body.get('kind')!='graph-source-revision' or body.get('node_id')!=scope['node_id']
                or body.get('ontology_id')!=identifier or body.get('limited') is not False
                or body.get('status')!='retained_graph' or not re.fullmatch(r'[0-9a-f]{64}',str(body.get('revision_sha256','')))):
                raise ValueError('Invalid selected graph revision receipt')
            receipts.append({key:body[key] for key in ('kind','node_id','ontology_id','revision_sha256','status','limited')})
            continue
        if (body.get('ontology_id') != identifier or
                not re.fullmatch(r'[0-9a-f]{64}', str(body.get('artifact_sha256', '')))):
            raise ValueError('Invalid ontology revision receipt')
        if body.get('status') == 'superseded' or body.get('lifecycle_status') in {'deprecated', 'retired'}:
            raise ValueError('Selected ontology is no longer current')
        receipts.append({key: body.get(key) for key in
            ('ontology_id', 'artifact_sha256', 'lifecycle_status', 'status', 'semantic_dependencies') if key in body})
    if scope.get('run_id') or scope.get('product_id'):
        from .selected_record import read
        _, receipt, _ = await read(scope, headers)
        receipts.append(receipt)
    return receipts


async def verify(record, headers):
    expected = record.get('source_revisions')
    if expected is None:
        return False  # Existing runs retain their previous source checks.
    current = await capture(record.get('scope') or {}, headers)
    if current != expected:
        raise ValueError('Selected source revision or lifecycle changed; start a new review')
    return True
