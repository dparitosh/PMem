"""Release coordination guard shared by native services; no second executor."""
import asyncio
from contextvars import copy_context
from contextlib import contextmanager
from functools import wraps
import inspect
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.bridge_contract import digest
from backend.depo_platform.service_urls import service_url
from backend.depo_platform.network import service_bearer_headers

REGISTRY_TYPE=PostgresRegistry
NAMESPACE='release_changes'

class ReleaseDependencyPending(ValueError):
    """Known pre-dispatch dependency failure; not an uncertain native write."""
    pass

FAMILIES={'merges':'ontology_merge_previews','bridges':'semantic_bridge_jobs_v1','publications':'ontology_publication_jobs_v1',
          'pipeline':'data_job_runs','product_changes':'data_product_approvals'}


def registry():return PostgresRegistry(NAMESPACE)
def binding_key(kind,identifier):return 'binding:'+kind+':'+identifier


def native(kind,identifier):
    if kind not in FAMILIES:raise HTTPException(422,'Unsupported release operation')
    value=PostgresRegistry(FAMILIES[kind]).get('request:'+identifier if kind=='product_changes' else identifier)
    if not value or not isinstance(value.get('change_request'),dict):raise HTTPException(409,'Prepare and submit the native operation before linking it')
    return value


def step_snapshot(kind,identifier):
    value=native(kind,identifier);change=value['change_request']
    if change.get('request_id')!=identifier:raise HTTPException(409,'Native request identity mismatch')
    return {'source_kind':kind,'identifier':identifier,'plan_digest':change['plan_digest']}


def retained_receipt(step):
    from backend.oslc_service.change_control import normalize
    value=native(step['source_kind'],step['identifier']);change=value['change_request']
    if change.get('plan_digest')!=step['plan_digest'] or change.get('state')!='executed':return False
    summary=normalize(step['source_kind'],value)
    if step['source_kind']=='merges':
        from backend.oslc_service.change_dossier import build_dossier
        return build_dossier('merges',value,summary,'urn:release-step').get('release',{}).get('native_result_linked') is True
    return summary.get('receipt_retained') is True


def baseline(record):
    identifier=record.get('configuration_id')
    if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{64}',identifier):raise HTTPException(409,'Release configuration identity is invalid')
    value=registry().get('baseline:'+identifier)
    if not value or value.get('kind')!='release-baseline' or value.get('configuration_id')!=record['configuration_id'] or digest(value.get('selections'))!=record['configuration_id']:
        raise HTTPException(409,'Release configuration integrity failed; restore the frozen baseline')
    return value


def valid_order(record):
    order=record.get('order')
    if not isinstance(order,dict) or not isinstance(record.get('configuration_id'),str) or not re.fullmatch('[0-9a-f]{64}',record['configuration_id']):return False
    from backend.depo_platform.approval_matrix import order_valid as matrix_order_valid
    return (matrix_order_valid(record) and record.get('state') in {'authorized','completed'} and order.get('request_id')==record.get('request_id')
        and order.get('operation')=='coordinate_source_to_release' and order.get('configuration_id')==record.get('configuration_id') and isinstance(order.get('authorized_by'),str)
        and bool(order['authorized_by'].strip()))


def graph_get(service,path,*,download=False):
    defaults={'GRAPH_SERVICE_URL':'http://127.0.0.1:8013/api/v1','ONTOLOGY_SERVICE_URL':'http://127.0.0.1:8011/api/v1','DATA_PRODUCT_SERVICE_URL':'http://127.0.0.1:8017/api/v1','DATA_CATALOG_URL':'http://127.0.0.1:8016/api/v1'}
    root=service_url(service,defaults[service]).rstrip('/')
    if not root.endswith('/api/v1'):root+='/api/v1'
    endpoint=root+path
    try:
        from backend.depo_platform.operations import current_operation
        operation_context=current_operation()
        timeout=operation_context.timeout(20) if operation_context else 20
        with httpx.Client(timeout=timeout,trust_env=False,follow_redirects=False) as client:
            headers=service_bearer_headers('GRAPH_READ_TOKEN',service_name='release evidence',endpoint=endpoint)
            if download:
                with client.stream('GET',endpoint,headers=headers) as response:
                    return response.status_code==200 and response.headers.get('content-type','').startswith('application/zip')
            response=client.get(endpoint,headers=headers);response.raise_for_status();return response.json()
    except (httpx.HTTPError,ValueError,RuntimeError,TimeoutError):raise HTTPException(503,'Native release evidence is unavailable; no step was executed') from None


def confirm(step):
    """Read native current receipts, never call a mutation for verification."""
    if not retained_receipt(step):return False
    kind=step['source_kind'];key=step['identifier'];value=native(kind,key)
    if kind=='product_changes':
        if not graph_get('DATA_PRODUCT_SERVICE_URL','/data-products/'+quote(key,safe='')+'/download',download=True):return False
        publication=value['publication']
        catalog=graph_get('DATA_CATALOG_URL','/catalog/products/'+quote(publication['product_id'],safe='')+'/versions/'+quote(publication['version'],safe=''))
        return isinstance(catalog,dict) and catalog.get('product_id')==publication['product_id'] and catalog.get('version')==publication['version'] and catalog.get('lifecycle_state')=='published' and (catalog.get('manifest') or {}).get('publication_digest')==value['plan_digest']
    if kind=='merges':
        result=graph_get('ONTOLOGY_SERVICE_URL','/ontologies/merges/'+quote(key,safe='')+'/receipt')
        return isinstance(result,dict) and result.get('preview_id')==key and (result.get('ontology') or {}).get('ontology_id')==value['change_request'].get('result_ontology_id')
    if kind=='bridges':
        result=graph_get('GRAPH_SERVICE_URL','/graph/bridge/publications/'+quote(key,safe=''))
        return isinstance(result,dict) and result.get('publication_id')==key and result.get('request_digest')==value.get('request_digest') and result.get('approved_by')==value.get('approved_by') and type(result.get('applied_links')) is int and result['applied_links']==len(value.get('approved_ids',[]))
    if kind=='publications':scope=key;publication=value['artifact_sha256']
    else:
        scope=(value.get('output_manifest') or {}).get('publication',{}).get('ontology_id');publication=key
    if not isinstance(scope,str) or not scope:return False
    result=graph_get('GRAPH_SERVICE_URL','/graph/ontologies/'+quote(scope,safe='')+'/publications/'+quote(publication,safe=''))
    return isinstance(result,dict) and result.get('status')=='published' and result.get('current') is True and result.get('ontology_id')==scope and result.get('publication_id')==publication and all(type(result.get(field)) is int and result[field]>=0 for field in ('resources','relationships'))


def tracking_snapshot():
    from backend.Services.oslc_trs_service import OSLCTRSService
    if not OSLCTRSService.is_enabled():raise HTTPException(409,'Enable TRS tracking before authorizing a coordinated release')
    state=OSLCTRSService._load()
    return {'stream_id':state['stream_id'],'order':state['counter']}


def bounded_reads(function,items):
    """Bound concurrency and carry the request/lease deadline into each read worker."""
    items=list(items)
    if not items:return []
    with ThreadPoolExecutor(max_workers=min(4,len(items))) as executor:
        futures=[executor.submit(copy_context().run,function,item) for item in items]
        return [future.result() for future in futures]


def source_snapshot(run_id):
    from backend.artifact_store import ArtifactStore
    import hashlib
    value=PostgresRegistry('data_job_runs').get(run_id)
    if not value or value.get('status')!='completed':raise HTTPException(409,'Select a completed retained source run')
    output=value.get('output_manifest') or {};artifacts=output.get('partition_artifacts') or {}
    accepted=artifacts.get('accepted')
    if not isinstance(accepted,str):raise HTTPException(409,'The source run must retain its accepted semantic partition')
    try:
        metadata,path=ArtifactStore().resolve(accepted)
        with path.open('rb') as source:checksum=hashlib.file_digest(source,'sha256').hexdigest()
    except (OSError,ValueError):raise HTTPException(409,'Retained source evidence is missing or changed') from None
    return {'run_id':run_id,'job_id':value.get('job_id'),'job_version':value.get('job_version'),
        'input_digest':(value.get('input_manifest') or {}).get('payload_digest'),
        'accepted_artifact_id':accepted,'accepted_sha256':checksum}


def check(kind,identifier):
    binding=registry().get(binding_key(kind,identifier))
    if not binding:return
    record=registry().get(binding['request_id'])
    if not record or record.get('request_id')!=binding['request_id'] or not valid_order(record) or record['state']!='authorized' or record['configuration_id']!=binding['configuration_id']:
        raise HTTPException(409,'The source-to-release change must authorize this exact configuration before execution')
    selections=baseline(record)['selections'];steps=selections['operations']
    if tracking_snapshot()['stream_id']!=selections['tracking']['stream_id']:
        raise HTTPException(409,'TRS generation changed; review and rebase the release configuration before execution')
    if source_snapshot(selections['source']['run_id'])!=selections['source']:
        raise HTTPException(409,'Source evidence changed after release configuration was frozen')
    positions=[index for index,step in enumerate(steps) if step['source_kind']==kind and step['identifier']==identifier]
    if len(positions)!=1:raise HTTPException(409,'Operation is outside the authorized release configuration')
    position=positions[0];current=step_snapshot(kind,identifier)
    if current!=steps[position]:raise HTTPException(409,'Native operation scope changed after release authorization')
    # This does not authorize a native action. The owning service still checks its own order.
    if position:
        if not all(bounded_reads(confirm,steps[:position])):raise HTTPException(409,'Complete and verify preceding release operations before this step')


@contextmanager
def operation(kind,identifier,store):
    # In-memory adapters are explicit test doubles; production services require PostgreSQL.
    if not isinstance(store,REGISTRY_TYPE):yield;return
    with registry().advisory_lock(binding_key(kind,identifier)) as acquired:
        if not acquired:raise HTTPException(409,'This release operation is being linked or updated; refresh')
        check(kind,identifier);yield


def guarded(resolve):
    """Hold the binding lock for native mutation so cancellation cannot race a write."""
    def decorate(fn):
        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def wrapped(*args,**kwargs):
                context=operation(*resolve(*args,**kwargs));executor=ThreadPoolExecutor(max_workers=1)
                entering=executor.submit(copy_context().run,context.__enter__);loop=asyncio.get_running_loop()
                try:
                    await asyncio.shield(asyncio.wrap_future(entering))
                    return await fn(*args,**kwargs)
                finally:
                    def close():
                        try:entering.result()
                        except BaseException:return
                        context.__exit__(None,None,None)
                    try:await asyncio.shield(loop.run_in_executor(executor,close))
                    finally:executor.shutdown(wait=False)
            return wrapped
        @wraps(fn)
        def wrapped(*args,**kwargs):
            with operation(*resolve(*args,**kwargs)):return fn(*args,**kwargs)
        return wrapped
    return decorate
