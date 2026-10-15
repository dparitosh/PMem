"""Serialized vocabulary publication with retained identity and receipt reconciliation."""
import asyncio
import hashlib
from .vocabulary_service import vocabularies


def publish(scheme_id, version, actor):
    key = vocabularies.key(scheme_id, version)
    with vocabularies.store.advisory_lock('publish:' + key) as acquired:
        if not acquired:
            raise ValueError('Vocabulary publication is active; refresh before retrying')
        record = vocabularies.get(scheme_id, version)
        if not record:
            raise LookupError('Vocabulary release was not found')
        if record.get('lifecycle_status') not in {'approved', 'published'}:
            raise ValueError('Only an approved vocabulary can be published')
        attempt = record.get('publication_attempt')
        if not attempt:
            if record.get('publication_status') == 'published':
                raise ValueError('Legacy publication has no retained receipt identity; reconcile it before republishing')
            artifact, content = vocabularies.publication_artifact(record)
            attempt = {'ontology_id':f"skos-{scheme_id}-{version.replace('.', '-')}",
                       'publication_id':hashlib.sha256(content).hexdigest(), 'artifact_id':artifact['artifact_id']}
            updated = {**record, 'publication_attempt':attempt}
            if not vocabularies.store.compare_and_put(key, record, updated):
                raise ValueError('Vocabulary changed before publication; reload')
            record = updated
        else:
            artifact, path = vocabularies.artifacts.resolve(attempt['artifact_id'])
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != attempt['publication_id']:
                raise ValueError('Retained vocabulary artifact changed; publication refused')
        try:
            receipt = asyncio.run(_publish(attempt, artifact, content))
            return vocabularies.mark_published(record, actor, artifact, receipt)
        except Exception:
            vocabularies.store.compare_and_put(key, record, {**record, 'publication_status':'unverified'})
            raise


def valid_receipt(receipt, attempt):
    return (isinstance(receipt, dict) and receipt.get('status') == 'published'
            and receipt.get('current') is True and receipt.get('ontology_id') == attempt['ontology_id']
            and receipt.get('publication_id') == attempt['publication_id']
            and all(type(receipt.get(field)) is int and receipt[field] >= 0 for field in ('resources','relationships')))


async def _publish(attempt, artifact, content):
    import httpx
    from backend.depo_platform.network import graph_dispatch_timeout_seconds, http_timeout, service_bearer_headers
    from backend.depo_platform.operations import current_operation
    from backend.depo_platform.service_urls import service_url
    base = service_url('GRAPH_SERVICE_URL','http://127.0.0.1:8013/api/v1')
    if not base.endswith('/api/v1'): base += '/api/v1'
    endpoint = f"{base}/graph/ontologies/{attempt['ontology_id']}/publications/{attempt['publication_id']}"
    budget = graph_dispatch_timeout_seconds() + 30
    operation = current_operation()
    if operation: budget = operation.timeout(budget)
    async with asyncio.timeout(budget), httpx.AsyncClient(timeout=http_timeout(budget),trust_env=False) as client:
        read_headers = service_bearer_headers('GRAPH_READ_TOKEN',service_name='vocabulary receipt',endpoint=endpoint)
        response = await client.get(endpoint,headers=read_headers)
        if response.status_code == 200:
            receipt = response.json()
            if not valid_receipt(receipt,attempt): raise RuntimeError('Vocabulary receipt is invalid or superseded')
            return receipt
        if response.status_code != 404:
            raise RuntimeError('Vocabulary publication outcome is unverified; wait and verify its receipt')
        missing = response.json()
        if not isinstance(missing,dict): raise RuntimeError('Invalid vocabulary receipt response')
        if missing.get('detail') != 'Publication receipt was not found' or missing.get('publication_idle') is not True:
            raise RuntimeError('Vocabulary graph publication is active or cannot be verified')
        response = await client.post(f'{base}/graph/ontologies/publish',
            data={**{key:attempt[key] for key in ('ontology_id','publication_id')},'prefix':'skos'},
            files={'artifact':(artifact['filename'],content,'text/turtle')},
            headers=service_bearer_headers('GRAPH_PUBLICATION_TOKEN',service_name='vocabulary publication',endpoint=base))
        response.raise_for_status()
        response = await client.get(endpoint,headers=read_headers)
        response.raise_for_status()
        receipt = response.json()
        if not valid_receipt(receipt,attempt): raise RuntimeError('Vocabulary graph receipt could not be verified')
        return receipt
