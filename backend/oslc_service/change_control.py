"""Central, read-only change evidence. Native services retain write authority."""
from urllib.parse import quote
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.authorization import graph_read_identity
from backend.Services.oslc_service import OSLCService
from .representation import represent

SOURCES = {
    'merges': ('ontology_merge_previews', 'Ontology merge', 'ontology', '/ontology?view=alignment&mode=merge'),
    'bridges': ('semantic_bridge_jobs_v1', 'Instance mapping', 'agentic', '/ontology?view=alignment'),
    'publications': ('ontology_publication_jobs_v1', 'Ontology publication', 'ontology', '/ontology'),
    'pipeline': ('data_job_runs', 'Data Flow run', 'dataPipeline', '/data-flow'),
    'products': ('data_products', 'Product release', 'dataProducts', '/data-products'),
    'learning': ('agentic_learning_reviews_v1', 'Learning review', 'agentic', '/ontology?view=alignment'),
}
FAILED = {'failed', 'timed_out', 'reconciliation_required', 'retryable', 'interrupted'}
router = APIRouter(tags=['Change control evidence'], dependencies=[Depends(graph_read_identity)])
log = logging.getLogger(__name__)
SUMMARY_FIELDS = ('preview_id','job_id','run_id','review_id','lesson_id','outcome_id','ontology_id',
    'product_id','version','ontology_name','name','status','approved_by','reviewed_by',
    'catalog_registered_at','updated_at','finished_at','published_at','created_at','started_at',
    'import_task_id','artifact_sha256','preview_digest','request_digest','publication_digest','governance_policy_sha256')
SUMMARY_PROJECTION = {field:[field] for field in SUMMARY_FIELDS} | {
    'applied_result':['applied_result','ontology','ontology_id'],
    'policy_verdict':['governance_audit','overall_verdict'],
    'governance_verdict':['governance','overall_verdict'],
    'receipt_publication_id':['receipt','publication_id'], 'receipt_request_digest':['receipt','request_digest'],
    'result_publication_id':['result','publication_id'], 'result_ontology_id':['result','ontology_id'],
    'approval_policy':['approval_policy','status'],
}


def restore_summary(row):
    """Reconstruct only small receipt fields; never retrieve preview bodies or tool output."""
    row = dict(row)
    if 'receipt_publication_id' in row:
        row['receipt'] = {'publication_id':row.pop('receipt_publication_id'), 'request_digest':row.pop('receipt_request_digest',None)}
        row['result'] = {'publication_id':row.pop('result_publication_id',None), 'ontology_id':row.pop('result_ontology_id',None)}
        row['governance'] = {'overall_verdict':row.pop('policy_verdict',None) or row.pop('governance_verdict',None)}
    return row


def identifier(kind, record):
    if kind == 'pipeline':
        return record.get('run_id')
    if kind == 'learning':
        return record.get('lesson_id') or record.get('outcome_id')
    if kind == 'publications':
        return record.get('ontology_id')
    if kind == 'products':
        return f"{record['product_id']}:{record['version']}" if record.get('product_id') and record.get('version') else None
    return next((record.get(key) for key in ('preview_id', 'job_id', 'run_id', 'review_id') if record.get(key)), None)


def normalize(kind, record):
    key = identifier(kind, record)
    if not isinstance(key, str) or not key or len(key) > 300:
        return None
    _, category, owner, route = SOURCES[kind]
    raw = str(record.get('status') or ('applied' if record.get('applied_result') else 'preview_ready' if kind == 'merges' else 'unknown'))[:80]
    actor = record.get('approved_by')
    authorized = isinstance(actor, str) and bool(actor.strip())
    receipt = record.get('receipt') if kind == 'bridges' else record.get('result') if kind == 'publications' else None
    receipt_retained = isinstance(receipt, dict) and bool(receipt.get('publication_id')) and raw == 'published'
    if kind == 'publications' and receipt_retained:
        receipt_retained = receipt.get('ontology_id') == record.get('ontology_id') and receipt.get('publication_id') == record.get('artifact_sha256')
    if kind == 'bridges' and receipt_retained:
        receipt_retained = receipt.get('publication_id') == record.get('job_id') and receipt.get('request_digest') == record.get('request_digest') and bool(record.get('request_digest'))
    if kind == 'pipeline':
        review = 'Evidence only; not approval'
    else:
        review = 'Authorization retained' if authorized else 'No authorization recorded'
    if kind == 'learning':
        review = 'Advisory lesson approved' if raw == 'approved' else 'Advisory lesson revoked' if raw == 'revoked' else 'Evidence only; not approval'
    execution = 'Needs recovery' if raw in FAILED else 'Applied to registry' if record.get('applied_result') else raw.replace('_', ' ').capitalize()
    delivery = 'Publication receipt retained' if receipt_retained else 'Not verified'
    if kind == 'products':
        delivery = 'Catalog delivery retained' if raw == 'published' and record.get('catalog_registered_at') else 'Catalog delivery pending' if raw == 'pending_catalog_registration' else 'Not verified'
    if kind == 'pipeline':
        route = '/data-flow/' + quote(key, safe='')
    elif kind == 'products':
        route = '/data-products'
    elif record.get('ontology_id') and kind == 'publications':
        route = '/ontology?target=' + quote(str(record['ontology_id']), safe='')
    evidence = {field: str(record[field])[:300] for field in
                ('ontology_id', 'import_task_id', 'preview_id', 'run_id', 'job_id', 'product_id', 'version',
                 'artifact_sha256', 'preview_digest', 'request_digest', 'publication_digest', 'governance_policy_sha256')
                if isinstance(record.get(field), (str, int))}
    policy = record.get('governance_audit') or record.get('governance') or {}
    verdict = str(policy.get('overall_verdict') or 'Not recorded')[:80] if isinstance(policy, dict) else 'Not recorded'
    return {'identifier':key, 'record_key':kind + ':' + key, 'category':category, 'source_kind':kind,
            'owner_service':owner, 'title':str(record.get('ontology_name') or record.get('name') or record.get('job_id') or key)[:240],
            'source_status':raw, 'review_state':review, 'execution_state':execution, 'delivery_state':delivery,
            'authorization_kind':'Advisory review; no publication authority' if kind == 'learning' else ('Delegated policy' if record.get('approval_policy') else 'Service authorization') if authorized else 'Not recorded',
            'authorization_actor':str(record.get('reviewed_by') or '')[:200] if kind == 'learning' else actor[:200] if authorized else None,
            'policy_assessment':verdict,
            'updated_at':str(record.get('updated_at') or record.get('finished_at') or record.get('published_at') or record.get('created_at') or record.get('started_at') or '')[:80],
            'workspace':'#' + route, 'evidence':evidence, 'receipt_retained':receipt_retained,
            'needs_attention':raw in FAILED, 'read_only':True,
            'currentness':'Retained evidence; revalidate in the owning workflow before any new execution',
            'type':'oslc_cm:ChangeRequest' if kind == 'merges' else 'urn:depo:change-control:EvidenceRecord'}


def collect(source='all', limit=25, offset=0, registry_factory=PostgresRegistry):
    selected = SOURCES if source == 'all' else {source:SOURCES[source]}
    records, coverage = [], []
    for kind, (namespace, *_rest) in selected.items():
        try:
            registry = registry_factory(namespace)
            options = {'projection':SUMMARY_PROJECTION} if isinstance(registry, PostgresRegistry) else {}
            total, rows = registry.page(limit=limit, offset=offset, exclude_latest=True, **options)
            rows = [restore_summary(row) if isinstance(row,dict) else row for row in rows]
            mapped = [normalize(kind, row) for row in rows if isinstance(row, dict)]
            records.extend(row for row in mapped if row is not None)
            coverage.append({'source':kind, 'status':'available', 'loaded':len(rows), 'limit':limit,
                             'total':total, 'has_more':offset + limit < total,
                             'unrecognized':sum(row is None for row in mapped)})
        except Exception as exc:
            # Never expose DSNs, SQL, paths, keys or untrusted exception text.
            coverage.append({'source':kind, 'status':'unavailable', 'loaded':0, 'limit':limit})
            log.warning('Change evidence source %s unavailable (%s)', kind, type(exc).__name__)
    records.sort(key=lambda row:(row['updated_at'], row['record_key']), reverse=True)
    return {'records':records, 'coverage':coverage, 'partial':any(row['status']!='available' for row in coverage),
            'offset':offset, 'limit':limit, 'has_more':any(row.get('has_more') for row in coverage),
            'read_only':True, 'counts_scope':'Loaded recent records per source; not all history or distinct end-to-end changes',
            'control_scope':'Visibility phase: approvals and execution remain in their owning workflows; no central approval is implied'}


@router.get('/api/v1/change-control/records')
@router.get('/oslc/change-control/records')
def records(request: Request, source: str = Query('all'), limit: int = Query(25, ge=1, le=50), offset: int = Query(0,ge=0,le=100000)):
    if request.url.path.startswith('/oslc/') and not OSLCService.is_enabled():
        raise HTTPException(404, 'OSLC integration is disabled')
    if source != 'all' and source not in SOURCES:
        raise HTTPException(422, 'Unknown change evidence source')
    payload = collect(source, limit, offset)
    root = OSLCService.config().base_url.rstrip('/') + '/oslc/change-control/records'
    for record in payload['records']:
        record['uri'] = root + '/' + record['source_kind'] + '/' + quote(record['identifier'], safe='')
    if all(row['status']=='unavailable' for row in payload['coverage']):
        raise HTTPException(503, 'Change evidence services are unavailable; no approval or execution state could be verified')
    if request.url.path.startswith('/oslc/'):
        payload = {key:value for key,value in payload.items() if key != 'records'} | {'members':payload['records']}
    return represent({**payload, 'uri':root, 'type':'oslc:QueryResult'}, request)


@router.get('/api/v1/change-control/records/{source}/{identifier}')
@router.get('/oslc/change-control/records/{source}/{identifier}')
def record(source: str, identifier: str, request: Request):
    if request.url.path.startswith('/oslc/') and not OSLCService.is_enabled():
        raise HTTPException(404, 'OSLC integration is disabled')
    if source not in SOURCES or len(identifier)>300:
        raise HTTPException(404, 'Change evidence record not found')
    try:
        value = PostgresRegistry(SOURCES[source][0]).get(identifier)
    except Exception:
        raise HTTPException(503, 'Change evidence is unavailable') from None
    result = normalize(source, value) if isinstance(value, dict) else None
    if result is None or result['identifier'] != identifier:
        raise HTTPException(404, 'Change evidence record not found')
    result['uri'] = OSLCService.config().base_url.rstrip('/') + '/oslc/change-control/records/' + source + '/' + quote(identifier, safe='')
    return represent(result, request)
