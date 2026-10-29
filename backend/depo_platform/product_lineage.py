"""Bounded, owner-resolved lineage for product publication; never follows user URLs."""
import asyncio
import re
import httpx
import hashlib
import json
from urllib.parse import quote
from .peer_http import async_peer_response
from .service_urls import service_url
from .network import service_bearer_headers

ARTIFACT = re.compile(r'sha256:[0-9a-f]{64}')


def validate_lineage(payload):
    for field in ('sources', 'ontologies'):
        values = payload.get(field, [])
        if not isinstance(values, list) or len(values) > 32:
            raise ValueError(field + ' must contain at most 32 typed references')
        for item in values:
            if not isinstance(item, dict):
                raise ValueError(field + ' entries must be objects with artifact_id, ontology_id or run_id')
            keys = ('ontology_id',) if field == 'ontologies' else ('artifact_id','ontology_id','run_id')
            if not any(isinstance(item.get(key), str) and item[key].strip() for key in keys):
                raise ValueError(field + ' reference has no owning source identity')
            if any(key in item for key in ('url','endpoint','headers','credentials')):
                raise ValueError('Lineage cannot override service routes or credentials')
            for key in ('ontology_id','run_id'):
                if key in item and (not isinstance(item[key], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', item[key])):
                    raise ValueError('Invalid lineage ' + key)
            if item.get('artifact_id') is not None and (not isinstance(item['artifact_id'], str) or not ARTIFACT.fullmatch(item['artifact_id'])):
                raise ValueError('Lineage artifact_id must be a SHA-256 content address')


def artifact_ids(value):
    if isinstance(value, dict):
        return set().union(*(artifact_ids(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(artifact_ids(v) for v in value)) if value else set()
    return {value} if isinstance(value, str) and ARTIFACT.fullmatch(value) else set()


async def resolve_lineage(payload, artifacts):
    validate_lineage(payload)
    packaged = {record['artifact_id'] for record, _ in artifacts}
    identities = {}
    for field in ('sources','ontologies'):
        for ref in payload.get(field) or []:
            if ref.get('ontology_id'): identities[('ontology',ref['ontology_id'])] = None
            if ref.get('run_id'): identities[('pipeline',ref['run_id'])] = None
            if not ref.get('ontology_id') and not ref.get('run_id') and ref.get('artifact_id') not in packaged:
                raise ValueError('Source artifact must be included in this product package')
    semaphore = asyncio.Semaphore(4)
    async def resolve(key):
        owner, identity = key
        variable, default, route = ('ONTOLOGY_SERVICE_URL','http://127.0.0.1:8011/api/v1','ontologies') if owner == 'ontology' else ('DATA_PIPELINE_SERVICE_URL','http://127.0.0.1:8019/api/v1','pipeline/jobs/runs')
        root = service_url(variable,default).rstrip('/')
        if not root.endswith('/api/v1'): root += '/api/v1'
        endpoint = root + '/' + route + '/' + quote(identity,safe='')
        async with semaphore:
            try:
                response = await async_peer_response('GET',endpoint,
                    headers=service_bearer_headers('GRAPH_READ_TOKEN',service_name='product lineage',endpoint=root),
                    budget=10,response_limit=8*1024*1024)
            except (TimeoutError, OSError, httpx.HTTPError) as exc:
                raise RuntimeError('Lineage owner is unavailable; publication was not attempted') from exc
            if response.status_code == 404: raise ValueError('Lineage reference does not exist: ' + owner + ':' + identity)
            if response.status_code != 200: raise RuntimeError('Lineage owner could not verify the reference')
            try: record = response.json()
            except ValueError as exc: raise RuntimeError('Lineage owner returned invalid JSON') from exc
            if not isinstance(record,dict) or record.get('ontology_id' if owner == 'ontology' else 'run_id') != identity:
                raise ValueError('Lineage owner response identity does not match')
            if owner == 'pipeline' and record.get('status') != 'completed': raise ValueError('Product evidence requires a completed source run')
            owned = artifact_ids(record)
            if not packaged.intersection(owned): raise ValueError('Packaged artifacts do not belong to the referenced source')
            identities[key] = record
    try:
        async with asyncio.timeout(30):
            tasks = [asyncio.create_task(resolve(key)) for key in identities]
            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done(): task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
    except TimeoutError as exc:
        raise RuntimeError('Lineage verification deadline exceeded; publication was not attempted') from exc
    for field in ('sources','ontologies'):
        for ref in payload.get(field) or []:
            for owner,key in [('ontology','ontology_id'),('pipeline','run_id')]:
                if ref.get(key) and ref.get('artifact_id') and ref['artifact_id'] not in artifact_ids(identities[(owner,ref[key])]):
                    raise ValueError('Source artifact does not match its owning record')
    return {'status':'resolved' if identities else 'artifact_only','owner_references':len(identities),
            'artifacts_verified':len(packaged),'graph_publication_verified':False,
            'resolved_sources':[{'owner':owner,'identity':identity,
                'record_sha256':hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                'artifact_ids':sorted(artifact_ids(record)),
                'status':record.get('status'),'lifecycle_status':record.get('lifecycle_status')}
                for (owner,identity),record in sorted(identities.items())]}
