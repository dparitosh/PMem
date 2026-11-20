"""Central, read-only change evidence. Native services retain write authority."""
from urllib.parse import quote
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.authorization import graph_read_identity
from backend.Services.oslc_service import OSLCService
from .representation import represent
from backend.ontology_service.merge_plan import valid_merge_order

SOURCES = {
    'releases':('release_changes','Source-to-release change','oslc','/change-control'),
    'merges': ('ontology_merge_previews', 'Ontology merge', 'ontology', '/ontology?view=alignment&mode=merge'),
    'bridges': ('semantic_bridge_jobs_v1', 'Instance mapping', 'agentic', '/ontology?view=alignment'),
    'publications': ('ontology_publication_jobs_v1', 'Ontology publication', 'ontology', '/ontology'),
    'import_changes':('tracked_import_changes_v1','Engineering record load','ingestion','/import'),
    'workflow_changes':('data_job_definition_changes_v1','Workflow maintenance change','dataPipeline','/change-control'),
    'definitions': ('data_job_definitions','Workflow definition','dataPipeline','/data-flow?view=pipelines'),
    'pipeline': ('data_job_runs', 'Data Flow run', 'dataPipeline', '/data-flow'),
    'product_changes': ('data_product_approvals', 'Product release request', 'dataProducts', '/data-products?view=governance'),
    'products': ('data_products', 'Product release', 'dataProducts', '/data-products'),
    'learning': ('agentic_learning_reviews_v1', 'Learning review', 'agentic', '/ontology?view=alignment'),
}
FAILED = {'failed', 'timed_out', 'reconciliation_required', 'retryable', 'interrupted'}
router = APIRouter(tags=['Change control evidence'], dependencies=[Depends(graph_read_identity)])
log = logging.getLogger(__name__)
SUMMARY_FIELDS = ('run_number','job_type','workflow_uuid','lifecycle_state','enabled','workflow_number','quality_profile','input_contract','output_contract','owner','approved_at','preview_id','job_id','run_id','review_id','lesson_id','outcome_id','ontology_id',
    'task_id','operation','product_id','version','request_id','request_number','source_name','job_name','source_system','source_standard','ontology_name','name','status','approved_by','reviewed_by',
    'catalog_registered_at','updated_at','finished_at','published_at','created_at','started_at',
    'import_task_id','artifact_sha256','preview_digest','request_digest','publication_digest','governance_policy_sha256')
SUMMARY_PROJECTION = {field:[field] for field in SUMMARY_FIELDS} | {
    'applied_result':['applied_result','ontology','ontology_id'],
    'policy_verdict':['governance_audit','overall_verdict'],
    'governance_verdict':['governance','overall_verdict'],
    'native_definition_receipt':['receipt','definition_sha256'], 'native_import_receipt':['receipt','plan_digest'],
    'receipt_publication_id':['receipt','publication_id'], 'receipt_request_digest':['receipt','request_digest'],
    'result_publication_id':['result','publication_id'], 'result_ontology_id':['result','ontology_id'],
    'approval_policy':['approval_policy','status'],
    'product_plan':['plan_digest'], 'product_receipt':['package_receipt'], 'merge_change':['change_request'], 'mapping_snapshot':['snapshot'],
    'accepted_partition':['output_manifest','partition_artifacts','accepted'],
    'pipeline_publication':['output_manifest','publication'],
    'pipeline_publication_intent':['output_manifest','publication_intent'],
    'pipeline_publication_digest':['output_manifest','publication_digest'],
}


def restore_summary(row):
    """Reconstruct only small receipt fields; never retrieve preview bodies or tool output."""
    row = dict(row)
    if 'product_plan' in row: row['plan_digest']=row.pop('product_plan')
    if 'product_receipt' in row: row['package_receipt']=row.pop('product_receipt')
    if 'mapping_snapshot' in row: row['snapshot']=row.pop('mapping_snapshot')
    if 'merge_change' in row: row['change_request'] = row.pop('merge_change')
    if 'receipt_publication_id' in row:
        row['receipt'] = {'publication_id':row.pop('receipt_publication_id'), 'request_digest':row.pop('receipt_request_digest',None)}
        row['result'] = {'publication_id':row.pop('result_publication_id',None), 'ontology_id':row.pop('result_ontology_id',None)}
        row['governance'] = {'overall_verdict':row.pop('policy_verdict',None) or row.pop('governance_verdict',None)}
    if 'pipeline_publication' in row:
        row['output_manifest'] = {'publication':row.pop('pipeline_publication'),
            'publication_intent':row.pop('pipeline_publication_intent',None),
            'publication_digest':row.pop('pipeline_publication_digest',None)}
    if 'accepted_partition' in row:
        accepted = row.pop('accepted_partition')
        if isinstance(accepted,str) and accepted:
            row.setdefault('output_manifest',{}).setdefault('partition_artifacts',{})['accepted']=accepted
    return row


def identifier(kind, record):
    if kind in {'product_changes','releases','workflow_changes'}:return record.get('request_id')
    if kind == 'import_changes':return record.get('task_id')
    if kind == 'bridges':
        return record.get('job_id')
    if kind == 'pipeline':
        return record.get('run_id')
    if kind == 'learning':
        return record.get('lesson_id') or record.get('outcome_id')
    if kind == 'publications':
        return record.get('ontology_id')
    if kind == 'definitions':
        return f"{record['job_id']}:{record['version']}" if record.get('job_id') and record.get('version') else None
    if kind == 'products':
        return f"{record['product_id']}:{record['version']}" if record.get('product_id') and record.get('version') else None
    return next((record.get(key) for key in ('preview_id', 'job_id', 'run_id', 'review_id') if record.get(key)), None)


def normalize(kind, record):
    if kind=='releases':
        from .release_changes import summary
        return summary(record)
    key = identifier(kind, record)
    if not isinstance(key, str) or not key or len(key) > 300:
        return None
    _, category, owner, route = SOURCES[kind]
    if kind == 'import_changes':
        from backend.ingestion_service.import_change import valid as valid_order
        change=record.get('change_request') or {};order=change.get('order') or {};authorized=valid_order(record)
        receipt_verified=bool(change.get('plan_digest')) and change.get('state')=='executed' and ((record.get('receipt') or {}).get('plan_digest')==change['plan_digest'] or record.get('native_import_receipt')==change['plan_digest'])
        return {'identifier':key,'record_key':kind+':'+key,'category':category,'source_kind':kind,'owner_service':owner,
            'title':str(record.get('name') or record.get('task_id') or key)[:240]+' · '+'Load retained records',
            'request_number':change.get('request_number'),'order_number':order.get('order_number'),
            'reason':change.get('reason'),'change_state':change.get('state'),'requested_by':change.get('requested_by'),'source_status':change.get('state'),'review_state':change.get('state','Not submitted'),
            'execution_state':'Import load receipt verified' if change.get('state')=='executed' else 'Awaiting authorized execution',
            'delivery_state':'Native load receipt verified' if receipt_verified else 'Load not verified','authorization_kind':'Service authorization' if authorized else 'Not authorized',
            'authorization_actor':order.get('authorized_by') if authorized else None,'policy_assessment':'Approval matrix',
            'updated_at':record.get('updated_at') or record.get('created_at') or '',
            'workspace':'#/import',
            'evidence':{'task_id':record.get('task_id'),'operation':'load_retained_import'},
            'receipt_retained':receipt_verified,'needs_attention':change.get('state')!='executed',
            'read_only':False,'currentness':'Exact retained import rows and mapping scope; native load receipt remains authoritative.',
            'type':'oslc_cm:ChangeRequest'}
    if kind == 'workflow_changes':
        from backend.data_pipeline_service.definition_changes import valid_order
        change=record.get('change_request') or {};order=change.get('order') or {};authorized=valid_order(record)
        return {'identifier':key,'record_key':kind+':'+key,'category':category,'source_kind':kind,'owner_service':owner,
            'title':str(record.get('name') or record.get('job_id') or key)[:240]+' · '+str(record.get('operation')),
            'request_number':change.get('request_number'),'order_number':order.get('order_number'),
            'reason':change.get('reason'),'change_state':change.get('state'),'requested_by':change.get('requested_by'),'source_status':change.get('state'),'review_state':change.get('state','Not submitted'),
            'execution_state':'Applied to workflow definition' if change.get('state')=='executed' else 'Awaiting authorized execution',
            'delivery_state':'No data publication','authorization_kind':'Service authorization' if authorized else 'Not authorized',
            'authorization_actor':order.get('authorized_by') if authorized else None,'policy_assessment':'Approval matrix',
            'updated_at':record.get('updated_at') or record.get('created_at') or '',
            'workspace':'#/data-flow?view=pipelines&definition_id='+quote(str(record.get('job_id') or ''),safe='')+'&definition_version='+quote(str(record.get('version') or ''),safe=''),
            'evidence':{'job_id':record.get('job_id'),'version':record.get('version'),'operation':record.get('operation')},
            'receipt_retained':bool((record.get('receipt') or {}).get('definition_sha256') or record.get('native_definition_receipt')) and change.get('state')=='executed','needs_attention':change.get('state')!='executed',
            'read_only':False,'currentness':'Exact retained workflow definition and schedule scope; no product release.',
            'type':'oslc_cm:ChangeRequest'}
    if kind == 'definitions':
        state=record.get('lifecycle_state')
        approved=state=='approved' and bool(record.get('approved_by'))
        enabled=approved and record.get('enabled') is True
        return {'identifier':key,'record_key':kind+':'+key,'category':category,'source_kind':kind,
            'owner_service':owner,'title':str(record.get('name') or record['job_id'])[:240],
            'reference':record.get('workflow_number'),'source_status':state,
            'review_state':'Approved definition' if approved else 'Disabled definition' if state=='disabled' else 'Definition review required',
            'execution_state':'Available for new runs' if enabled else 'New execution blocked',
            'delivery_state':'Not applicable to a definition','authorization_kind':'Workflow definition approval' if approved else 'Not recorded',
            'authorization_actor':record.get('approved_by') if approved else None,
            'policy_assessment':'Not assessed','updated_at':record.get('approved_at') or record.get('created_at') or '',
            'workspace':'#/data-flow?view=pipelines&definition_id='+quote(record['job_id'],safe='')+'&definition_version='+quote(record['version'],safe=''),
            'evidence':{field:str(record[field]) for field in ('job_id','version','workflow_uuid','workflow_number','job_type','owner','quality_profile','input_contract','output_contract') if record.get(field) is not None},
            'receipt_retained':False,'needs_attention':state not in {'approved','disabled'},'read_only':True,
            'currentness':'Definition approval permits new execution only; run inputs and publication approvals remain separate.',
            'type':'urn:depo:change-control:EvidenceRecord'}
    raw = str(record.get('status') or ('applied' if record.get('applied_result') else 'preview_ready' if kind == 'merges' else 'unknown'))[:80]
    actor = record.get('approved_by')
    change = record.get('change_request') if kind in {'merges','bridges','product_changes','pipeline','publications'} else None
    change = change if isinstance(change, dict) else {}
    order = change.get('order') or {}
    order_valid = valid_merge_order(change, key)
    if kind=='bridges' and change:
        from backend.agentic_service.bridge_change import retained_plan,valid_order
        retained=retained_plan(record)
        order_valid=bool(retained) and valid_order(change,record.get('preview_id'),key,retained)
    if kind=='publications' and change:
        from backend.ontology_service.publication_change import valid_order
        order_valid=valid_order(record)
    if kind=='pipeline' and change:
        from backend.data_pipeline_service.publication_change import valid_order
        order_valid=valid_order(record)
    if kind=='product_changes':
        from backend.data_product_service.product_change import valid_order
        order_valid=valid_order(record)
    if change: actor = order['authorized_by'] if order_valid else None
    authorized = isinstance(actor, str) and bool(actor.strip())
    receipt = record.get('receipt') if kind == 'bridges' else record.get('result') if kind == 'publications' else None
    receipt_retained = isinstance(receipt, dict) and bool(receipt.get('publication_id')) and raw == 'published'
    if kind == 'publications' and receipt_retained:
        receipt_retained = receipt.get('ontology_id') == record.get('ontology_id') and receipt.get('publication_id') == record.get('artifact_sha256')
    if kind == 'bridges' and receipt_retained:
        receipt_retained = receipt.get('publication_id') == record.get('job_id') and receipt.get('request_digest') == record.get('request_digest') and bool(record.get('request_digest'))
    if kind == 'pipeline':
        from backend.data_pipeline_service.run_records import _digest
        output = record.get('output_manifest') or {}
        publication = output.get('publication') if isinstance(output, dict) else None
        intent = output.get('publication_intent') if isinstance(output, dict) else None
        receipt_retained = (isinstance(publication, dict) and isinstance(intent, dict) and
            publication.get('status') == 'published' and publication.get('publication_id') == key and
            isinstance(intent.get('ontology_id'), str) and bool(intent['ontology_id'].strip()) and
            publication.get('ontology_id') == intent['ontology_id'] and
            output.get('publication_digest') == _digest(publication))
        review = 'Authorization retained' if change and authorized else 'Evidence only; not approval'
    else:
        review = 'Authorization retained' if authorized else 'No authorization recorded'
    if kind == 'learning':
        review = 'Advisory lesson approved' if raw == 'approved' else 'Advisory lesson revoked' if raw == 'revoked' else 'Evidence only; not approval'
    if kind in {'merges','bridges','product_changes','pipeline','publications'} and change and not authorized:
        review = {'submitted':'Request awaiting review','accepted':'Request accepted; execution not authorized','rejected':'Request returned','cancelled':'Request cancelled'}.get(change.get('state'), review)
    execution = 'Needs recovery' if raw in FAILED else 'Applied to registry' if record.get('applied_result') else raw.replace('_', ' ').capitalize()
    if kind in {'merges','bridges','product_changes','pipeline','publications'} and change:
        execution = {'submitted':'Awaiting request review','accepted':'Awaiting release authorization','authorized':'Authorization recorded; verify current plan' if order_valid else 'Authorization evidence incomplete; review required','executing':'Executing authorized operation','needs_recovery':'Needs recovery','cancelled':'Cancelled','rejected':'Not executed'}.get(change.get('state'), execution)
    if kind=='product_changes' and change:
        execution={'awaiting_delivery':'Product package retained; delivery verification pending','executed':'Package and catalog delivery verified'}.get(change.get('state'),execution)
        package=record.get('package_receipt') or {}
        receipt_retained=bool(change.get('state')=='executed' and package.get('product_version')==key and package.get('publication_digest')==record.get('plan_digest') and package.get('status')=='published' and package.get('catalog_registered_at') and order_valid)
    if kind=='publications' and change:
        verified=change.get('receipt') or {}
        receipt_retained=bool(receipt_retained and order_valid and change.get('state')=='executed' and verified.get('current') is True and verified.get('ontology_id')==key and verified.get('publication_id')==record.get('artifact_sha256'))
        if change.get('state')=='executed':execution='Graph publication receipt verified' if receipt_retained else 'Publication evidence incomplete; verification required'
    if kind=='pipeline' and change:
        verified=change.get('receipt') or {}
        receipt_retained=bool(receipt_retained and order_valid and change.get('state')=='executed' and verified.get('current') is True and verified.get('publication_id')==key and verified.get('ontology_id')==((change.get('plan') or {}).get('intent') or {}).get('ontology_id'))
        if change.get('state')=='executed':execution='Graph publication receipt verified' if receipt_retained else 'Publication evidence incomplete; verification required'
    delivery = 'Publication receipt retained' if receipt_retained else 'Not verified'
    if kind == 'pipeline' and receipt_retained:
        delivery = 'Graph publication receipt retained'
    if kind == 'products':
        delivery = 'Catalog delivery retained' if raw == 'published' and record.get('catalog_registered_at') else 'Catalog delivery pending' if raw == 'pending_catalog_registration' else 'Not verified'
    if kind == 'pipeline':
        route = '/data-flow/' + quote(key, safe='')
    elif kind == 'products':
        route = '/data-products'
    elif record.get('ontology_id') and kind == 'publications':
        route = '/ontology?target=' + quote(str(record['ontology_id']), safe='')
    evidence = {field: str(record[field])[:300] for field in
                ('source_system','job_type','ontology_id', 'import_task_id', 'preview_id', 'run_id', 'job_id', 'product_id', 'version',
                 'artifact_sha256', 'preview_digest', 'request_digest', 'publication_digest', 'governance_policy_sha256')
                if isinstance(record.get(field), (str, int))}
    policy = record.get('governance_audit') or record.get('governance') or {}
    verdict = str(policy.get('overall_verdict') or 'Not recorded')[:80] if isinstance(policy, dict) else 'Not recorded'
    title = str(record.get('ontology_name') or record.get('name') or record.get('job_name') or record.get('job_id') or key)[:240]
    if kind == 'pipeline':
        from backend.depo_platform.run_labels import source_name
        subject = source_name(record)
        title = ('Publish ' if change else 'Validate ') + subject if subject else 'Engineering data ' + ('publication' if change else 'validation')
    else:
        subject = str(record.get('ontology_name') or record.get('name') or '')[:240]
    source_ready=False
    if kind == 'pipeline':
        from backend.data_pipeline_service.publication_change import SEMANTIC_JOBS
        output=record.get('output_manifest') or {}
        partitions=output.get('partition_artifacts') or {}
        accepted=partitions.get('accepted')
        source_ready=raw=='completed' and record.get('job_type') in SEMANTIC_JOBS and isinstance(accepted,str) and bool(accepted.strip())
    return {'identifier':key, 'record_key':kind + ':' + key, 'category':category, 'source_kind':kind,
            'owner_service':owner, 'title':title, 'subject':subject, 'reason':str(change.get('reason') or '')[:500],
            'request_number':change.get('request_number'), 'order_number':order.get('order_number'),
            'change_state':change.get('state'), 'requested_by':change.get('requested_by'),
            'reference':record.get('run_number') if kind=='pipeline' else None,'release_source_ready':source_ready,
            'source_status':raw, 'review_state':review, 'execution_state':execution, 'delivery_state':delivery,
            'authorization_kind':'Advisory review; no publication authority' if kind == 'learning' else ('Delegated policy' if record.get('approval_policy') else 'Service authorization') if authorized else 'Not recorded',
            'authorization_actor':str(record.get('reviewed_by') or '')[:200] if kind == 'learning' else actor[:200] if authorized else None,
            'policy_assessment':verdict,
            'updated_at':str(record.get('updated_at') or record.get('finished_at') or record.get('published_at') or record.get('created_at') or record.get('started_at') or '')[:80],
            'workspace':'#' + route, 'evidence':evidence, 'receipt_retained':receipt_retained,
            'needs_attention':raw in FAILED or change.get('state') == 'needs_recovery' or bool(change and change.get('state') in {'authorized','executing','executed'} and not order_valid), 'read_only':True,
            'currentness':'Retained evidence; revalidate in the owning workflow before any new execution',
            'type':'oslc_cm:ChangeRequest' if kind == 'merges' or kind in {'bridges','product_changes','pipeline','publications'} and change else 'urn:depo:change-control:EvidenceRecord'}


def collect(source='all', limit=25, offset=0, registry_factory=PostgresRegistry):
    selected = SOURCES if source == 'all' else {source:SOURCES[source]}
    records, coverage = [], []
    for kind, (namespace, *_rest) in selected.items():
        try:
            registry = registry_factory(namespace)
            options = {'projection':SUMMARY_PROJECTION} if isinstance(registry, PostgresRegistry) else {}
            if kind=='product_changes':options.update(field='kind',value='release_change')
            if kind=='releases':options={'field':'kind','value':'release-change'}
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
            'control_scope':'Coordinated release requests bind exact native scopes; each owning service retains execution and publication authority'}


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
    if request.headers.get('configuration-context'):
        from .release_changes import contextual_selection
        return contextual_selection(request.headers['configuration-context'],source,identifier,request)
    try:
        value = PostgresRegistry(SOURCES[source][0]).get('request:'+identifier if source=='product_changes' else identifier)
    except Exception:
        raise HTTPException(503, 'Change evidence is unavailable') from None
    result = normalize(source, value) if isinstance(value, dict) else None
    if result is None or result['identifier'] != identifier:
        raise HTTPException(404, 'Change evidence record not found')
    result['uri'] = OSLCService.config().base_url.rstrip('/') + '/oslc/change-control/records/' + source + '/' + quote(identifier, safe='')
    from .change_dossier import build_dossier, digest
    result['dossier'] = build_dossier(source, value, result, result['uri'])
    from .media import negotiate
    media = negotiate(request.headers.get('accept', 'application/json'))
    if media is None:
        raise HTTPException(406, 'No supported OSLC representation is acceptable')
    # Semantic identity: RDF serializers may assign different blank-node labels.
    etag = 'W/"' + digest({'representation': media, 'record': result}) + '"'
    headers = {'ETag': etag, 'Cache-Control': 'private, no-cache', 'Vary': 'Accept, Authorization'}
    supplied = request.headers.get('if-none-match', '').strip()
    validators = [tag.strip().removeprefix('W/') for tag in supplied.split(',')]
    if supplied == '*' or etag.removeprefix('W/') in validators:
        return Response(status_code=304, headers=headers)
    response = represent(result, request)
    response.headers.update(headers)
    return response
