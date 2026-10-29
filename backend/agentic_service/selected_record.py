"""Exact owning-service reads for selected operational records; never graph guesses."""
import hashlib
import json
from urllib.parse import quote
from .companion_context import _read_json


async def read(scope, headers):
    run_id, product_id, version = (scope.get(key, '') for key in ('run_id', 'product_id', 'product_version'))
    if run_id and product_id:
        raise ValueError('Select one operational record at a time')
    if run_id:
        body, endpoint = await _read_json('DATA_PIPELINE_SERVICE_URL', 'http://127.0.0.1:8019',
            '/pipeline/jobs/runs/' + quote(run_id, safe=''), {}, headers)
        if body.get('run_id') != run_id:
            raise ValueError('Pipeline evidence changed selected run')
        kind, identifier = 'pipeline_run', run_id
    elif product_id:
        if version:
            identifier = product_id + ':' + version
            body, endpoint = await _read_json('DATA_PRODUCT_SERVICE_URL', 'http://127.0.0.1:8017',
                '/data-products/' + quote(identifier, safe=''), {}, headers)
            if body.get('product_id') != product_id or body.get('version') != version:
                raise ValueError('Product evidence changed selected version')
        else:
            identifier = product_id
            body, endpoint = await _read_json('DATA_CATALOG_URL', 'http://127.0.0.1:8016',
                '/catalog/products/' + quote(product_id, safe=''), {}, headers)
            if body.get('product_id') != product_id:
                raise ValueError('Catalog evidence changed selected product')
        kind = 'data_product'
    else:
        return None
    # Fingerprint authoritative state, including retained manifests and lifecycle;
    # never use client-provided labels as revision evidence.
    revision = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    return body, {'resource_kind': kind, 'resource_id': identifier, 'revision': revision}, endpoint


async def answer(scope, headers):
    result = await read(scope, headers)
    if result is None:
        return None
    body, receipt, endpoint = result
    from .business_answers import cell
    fields = ('name', 'description', 'status', 'lifecycle_state', 'version', 'job_id', 'job_version',
              'job_type', 'domain', 'source_system', 'source_standard', 'publication_status', 'owner')
    rows = [(key.replace('_', ' ').capitalize(), value) for key in fields
            if isinstance((value := body.get(key)), (str, int, float, bool))]
    text = f"Selected {'pipeline run' if scope.get('run_id') else 'data product'}: **{cell(body.get('name') or receipt['resource_id'])}**.\n\n| Detail | Recorded value |\n|---|---|"
    for key, value in rows:
        text += f'\n| {cell(key)} | {cell(str(value))} |'
    text += '\n\nThis describes the selected retained record. Unrecorded engineering associations and approvals have not been inferred.'
    resource_id = receipt['resource_kind'] + ':' + receipt['resource_id']
    return {'status': 'grounded', 'answerable': True, 'response': text + f'\n\n[evidence:{resource_id}]',
        'evidence': [{'resource_id': resource_id, 'label': body.get('name') or receipt['resource_id'],
                      'description': text, 'source': endpoint, 'record_revision': receipt['revision']}],
        'sources': [endpoint], 'retrieval': {'answer_scope': 'selected_operational_record', 'source_revision': receipt},
        'generation': {'enabled': False, 'status': 'not_requested'}}
