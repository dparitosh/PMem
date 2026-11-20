"""One source-to-release CR over ordered native operations and frozen selections."""
from contextlib import ExitStack
from copy import deepcopy
from urllib.parse import quote
from fastapi import APIRouter,Depends,HTTPException,Request,Response,Query
from backend.depo_platform.authorization import approval_identity,graph_read_identity
from backend.depo_platform.request_bodies import ReleaseChangeSubmission,ReleaseChangeCommand
from backend.depo_platform.change_requests import event
from backend.depo_platform import release_chain as chain
from backend.depo_platform.bridge_contract import digest
from backend.Services.oslc_service import OSLCService
from .representation import represent

router=APIRouter(tags=['Source-to-release change control'])


def configuration_uri(identifier):return '/oslc/change-control/configurations/'+identifier


def notice(record):
    key='notice:'+record['request_id']
    return {'kind':'release-notice','status':'pending','outbox_key':key,
        'delivery_id':key+':'+str(record['revision'])+':'+record['configuration_id'],
        'resource_uri':'/oslc/change-control/records/releases/'+quote(record['request_id'],safe=''),
        'event_type':'Creation' if record['revision']==1 else 'Modification','title':'Source-to-release change updated',
        'metadata':{'storage_key':record['request_id'],'identifier':record['request_id'],'revision':record['revision'],'configuration_id':record['configuration_id'],'state':record['state']}}


def save(record,extra=None):
    from backend.mesh_store import PostgresRegistry
    if isinstance(chain.registry(), PostgresRegistry):
        from backend.depo_platform.resource_identity import ensure
        ensure(record, 'releases', record['request_id'])
    record['updated_at']=record['history'][-1]['at']
    return chain.registry().put_many({record['request_id']:record,'notice:'+record['request_id']:notice(record),**(extra or {})})


def load(identifier):
    record=chain.registry().get(identifier)
    if not record or record.get('kind')!='release-change' or record.get('request_id')!=identifier:raise HTTPException(404,'Source-to-release change was not found')
    chain.baseline(record)
    return record


def selections(body):
    operations=[item.model_dump() for item in body.operations]
    identities=[(item['source_kind'],item['identifier']) for item in operations]
    if len(set(identities))!=len(identities):raise HTTPException(422,'Choose each operation once')
    if ('pipeline',body.source_run_id) not in identities or operations[-1]['source_kind']!='product_changes':
        raise HTTPException(422,'Include the selected source run publication and finish with its product release')
    snapshots=[]
    for item in operations:
        value=chain.native(**{'kind':item['source_kind'],'identifier':item['identifier']})
        if value['change_request'].get('state') not in {'submitted','accepted','authorized'}:
            raise HTTPException(409,'Link prepared operations before execution; historical results cannot be retroactively approved')
        snapshots.append(chain.step_snapshot(item['source_kind'],item['identifier']))
    product=chain.native('product_changes',operations[-1]['identifier'])['publication']
    if not any(isinstance(ref,dict) and ref.get('run_id')==body.source_run_id for ref in product.get('sources',[])):
        raise HTTPException(409,'The final product must retain lineage to the selected source run')
    source=chain.source_snapshot(body.source_run_id)
    artifact_ids={ref.get('artifact_id') for ref in product.get('artifacts',[]) if isinstance(ref,dict)}
    if source['accepted_artifact_id'] not in artifact_ids:raise HTTPException(409,'The final product must include the accepted source partition')
    return {'source':source,'operations':snapshots,'tracking':chain.tracking_snapshot()}


def create(body,actor):
    if not body.title.strip() or not body.reason.strip():raise HTTPException(422,'Provide the change title and business reason')
    # Lock each referenced operation before reading scopes and creating bindings.
    refs=[item.model_dump() for item in body.operations];store=chain.registry()
    with ExitStack() as stack:
        for item in sorted(refs,key=lambda row:(row['source_kind'],row['identifier'])):
            if not stack.enter_context(store.advisory_lock(chain.binding_key(item['source_kind'],item['identifier']))):
                raise HTTPException(409,'A selected native operation is active or being linked')
        identifier='release-'+digest({'title':body.title.strip(),'reason':body.reason.strip(),'source_run_id':body.source_run_id,'operations':refs})[:32]
        previous=store.get(identifier)
        if previous:return view(identifier)
        frozen=selections(body);configuration=digest(frozen)
        for item in frozen['operations']:
            if store.get(chain.binding_key(item['source_kind'],item['identifier'])):raise HTTPException(409,'A selected operation already belongs to another release change')
        record={'kind':'release-change','request_id':identifier,'title':body.title.strip(),'reason':body.reason.strip(),
            'source_run_id':body.source_run_id,'configuration_id':configuration,'revision':0,'state':'submitted',
            'requested_by':actor,'order':None,'history':[]}
        event(record,'submit',actor,body.reason.strip())
        baseline={'kind':'release-baseline','configuration_id':configuration,'selections':frozen,
            'configuration_context':configuration_uri(configuration),'approval_status':'Defined by the linked change order; baseline creation is not approval'}
        config_key='baseline:'+configuration
        config_notice='notice:configuration:'+configuration
        extra={config_key:baseline,config_notice:{'kind':'release-notice','status':'pending','outbox_key':config_notice,
            'delivery_id':config_notice,'resource_uri':configuration_uri(configuration),'event_type':'Creation',
            'title':'Frozen release configuration created','metadata':{'storage_key':config_key,'configuration_id':configuration}}}
        extra.update({chain.binding_key(item['source_kind'],item['identifier']):{'request_id':identifier,'configuration_id':configuration} for item in frozen['operations']})
        save(record,extra);return view(identifier)


def assessment(record,*,verify=False):
    frozen=chain.baseline(record)['selections'];steps=[];changed=False
    try:tracking_changed=chain.tracking_snapshot()['stream_id']!=frozen['tracking']['stream_id']
    except (HTTPException,RuntimeError):tracking_changed=True
    try:changed=chain.source_snapshot(frozen['source']['run_id'])!=frozen['source']
    except HTTPException:changed=True
    def assess_step(item):
        try:
            value=chain.native(item['source_kind'],item['identifier']);same=chain.step_snapshot(item['source_kind'],item['identifier'])==item
            retained=chain.retained_receipt(item) if same else False
            current=chain.confirm(item) if verify and retained else retained
            state=value['change_request']['state']
        except (HTTPException,RuntimeError):same=False;current=False;state='unavailable';value={}
        return {**item,'state':state,'scope_matches':same,'receipt_verified':current,
            'preview_id':value.get('preview_id') if state!='unavailable' and item['source_kind']=='bridges' else item['identifier']}
    steps=chain.bounded_reads(assess_step,frozen['operations'])
    changed=changed or any(not item['scope_matches'] for item in steps)
    return {'source_matches':not changed,'tracking_changed':tracking_changed,'scope_changed':changed or tracking_changed,'operations':steps,
        'complete':not changed and not tracking_changed and all(item['receipt_verified'] for item in steps)}


def view(identifier):
    record=load(identifier)
    return {**deepcopy(record),**assessment(record),'configuration_context':configuration_uri(record['configuration_id']),
        'configuration':chain.baseline(record),
        'authority':'One coordinated CR; each native approval, execution and receipt remains authoritative'}


def transition(identifier,payload,actor,context=None):
    store=chain.registry()
    with store.advisory_lock(identifier) as acquired:
        if not acquired:raise HTTPException(409,'This release is being reviewed; refresh')
        record=load(identifier);frozen=chain.baseline(record)['selections']
        if record['revision']!=payload.expected_revision or record['configuration_id']!=payload.configuration_id:
            raise HTTPException(409,'Release revision or configuration changed; refresh before deciding')
        allowed_context={configuration_uri(record['configuration_id']),OSLCService.config().base_url.rstrip('/')+configuration_uri(record['configuration_id'])}
        if context and context not in allowed_context:raise HTTPException(409,'Configuration-Context does not match the frozen release baseline')
        with ExitStack() as stack:
            for item in sorted(frozen['operations'],key=lambda row:(row['source_kind'],row['identifier'])):
                if not stack.enter_context(store.advisory_lock(chain.binding_key(item['source_kind'],item['identifier']))):raise HTTPException(409,'A native operation is active; verify its outcome before changing the release')
            action=payload.action
            if action=='rebase':
                if record['state'] in {'cancelled','rejected'}:raise HTTPException(409,'A cancelled or returned release cannot be rebased')
                if chain.source_snapshot(frozen['source']['run_id'])!=frozen['source'] or any(chain.step_snapshot(item['source_kind'],item['identifier'])!=item for item in frozen['operations']):
                    raise HTTPException(409,'Rebase cannot replace source or operation scope; prepare a new reviewed release')
                next_selections={**frozen,'tracking':chain.tracking_snapshot()}
                if next_selections==frozen:return view(identifier)
                previous=record['configuration_id'];configuration=digest(next_selections)
                if record.get('order'):record.setdefault('prior_orders',[]).append(record['order'])
                record.update(configuration_id=configuration,state='submitted',order=None)
                record.pop('receipt',None)
                event(record,'rebase_tracking',actor,payload.reason)
                baseline={'kind':'release-baseline','configuration_id':configuration,'selections':next_selections,
                    'configuration_context':configuration_uri(configuration),'predecessor_configuration':previous,'approval_status':'Reapproval required'}
                extras={'baseline:'+configuration:baseline}
                extras.update({chain.binding_key(item['source_kind'],item['identifier']):{'request_id':identifier,'configuration_id':configuration} for item in frozen['operations']})
                config_notice='notice:configuration:'+configuration
                extras[config_notice]={'kind':'release-notice','status':'pending','outbox_key':config_notice,'delivery_id':config_notice,
                    'resource_uri':configuration_uri(configuration),'event_type':'Creation','title':'Release configuration rebased',
                    'metadata':{'storage_key':'baseline:'+configuration,'configuration_id':configuration}}
                save(record,extras);return view(identifier)
            if action=='verify':
                if not chain.valid_order(record):raise HTTPException(409,'Authorize the release configuration before closing it')
                report=assessment(record,verify=True)
                if not report['complete']:raise HTTPException(409,'Not all exact native receipts and final delivery are verified; no action was replayed')
                if record['state']=='completed':return view(identifier)
                record['state']='completed';record['receipt']={'configuration_id':record['configuration_id'],'operations':report['operations'],'verified_by':actor}
            else:
                allowed={'accept':{'submitted'},'authorize':{'accepted'},'reject':{'submitted','accepted'},'cancel':{'submitted','accepted','authorized'}}
                if action not in allowed or record['state'] not in allowed[action]:raise HTTPException(409,'This decision is not allowed for the release state')
                if action in {'accept','authorize'} and assessment(record)['scope_changed']:raise HTTPException(409,'Source or operation scope changed; the frozen release cannot be approved')
                if action=='cancel' and any(chain.native(item['source_kind'],item['identifier'])['change_request'].get('state') in {'executing','needs_recovery','awaiting_delivery'} for item in frozen['operations']):raise HTTPException(409,'A native operation has already been dispatched; verify its outcome before cancelling future work')
                if action=='reject' and not payload.reason.strip():raise HTTPException(422,'Provide the reason for returning this change')
                record['state']={'accept':'accepted','authorize':'authorized','reject':'rejected','cancel':'cancelled'}[action]
                if action=='authorize':record['order']={'request_id':identifier,'configuration_id':record['configuration_id'],'authorized_by':actor,'operation':'coordinate_source_to_release'}
            event(record,action,actor,payload.reason);save(record);return view(identifier)


@router.post('/api/v1/change-control/releases')
def submit_release(payload: ReleaseChangeSubmission,request: Request):
    actor=approval_identity(request,{},token_env='DATA_JOB_APPROVAL_TOKEN')
    return create(payload,actor)


@router.get('/api/v1/change-control/releases/{identifier}',dependencies=[Depends(graph_read_identity)])
def release_status(identifier: str,request: Request):
    value=view(identifier);etag='W/"'+digest(value)+'"'
    if request.headers.get('if-none-match')==etag:return Response(status_code=304,headers={'ETag':etag,'Vary':'Accept, Authorization, Configuration-Context'})
    response=represent(value,request);response.headers['ETag']=etag;response.headers['Vary']='Accept, Authorization, Configuration-Context';return response


@router.post('/api/v1/change-control/releases/{identifier}')
def release_command(identifier: str,payload: ReleaseChangeCommand,request: Request):
    actor=approval_identity(request,{},token_env='DATA_JOB_APPROVAL_TOKEN')
    supplied=request.headers.get('if-match')
    if supplied and supplied!='W/"'+digest(view(identifier))+'"':raise HTTPException(412,'Release evidence changed; refresh before deciding')
    return transition(identifier,payload,actor,request.headers.get('configuration-context'))


@router.get('/oslc/change-control/configuration-shape',dependencies=[Depends(graph_read_identity)])
def configuration_shape(request: Request):
    root=OSLCService.config().base_url.rstrip('/')+'/oslc/change-control/configuration-shape'
    return represent({'uri':root,'type':'oslc:ResourceShape','describes':['http://open-services.net/ns/config#Baseline'],
        'properties':[{'name':'selections','propertyDefinition':'http://open-services.net/ns/config#selections',
                       'occurs':'http://open-services.net/ns/core#Exactly-one','readOnly':True,
                       'valueType':'http://open-services.net/ns/core#Resource',
                       'range':['http://open-services.net/ns/config#Selections']}]},request)


@router.get('/oslc/change-control/configurations',dependencies=[Depends(graph_read_identity)])
def configurations(request: Request, limit: int=Query(25,ge=1,le=100), offset: int=Query(0,ge=0)):
    root=OSLCService.config().base_url.rstrip('/')+'/oslc/change-control/configurations'
    total,rows=chain.registry().page(limit=limit,offset=offset,field='kind',value='release-baseline')
    members=[]
    for record in rows:
        identifier=record.get('configuration_id')
        if not identifier or digest(record.get('selections'))!=identifier:
            raise HTTPException(503,'Retained release baseline integrity failed; inspect configuration storage')
        members.append({'uri':root+'/'+identifier,'type':'oslc_config:Baseline','configuration_id':identifier})
    payload={'uri':root,'type':'oslc:QueryResult','members':members,'total':total,
             'scope':'Frozen release baselines; not streams or global configurations'}
    if offset+limit<total:payload['nextPage']=root+'?limit='+str(limit)+'&offset='+str(offset+limit)
    return represent(payload,request)


@router.get('/oslc/change-control/configurations/{identifier}',dependencies=[Depends(graph_read_identity)])
@router.get('/api/v1/change-control/configurations/{identifier}',dependencies=[Depends(graph_read_identity)])
def configuration(identifier: str,request: Request):
    record=chain.registry().get('baseline:'+identifier)
    if not record or record.get('kind')!='release-baseline' or digest(record.get('selections'))!=identifier:raise HTTPException(404,'Release configuration was not found')
    root=OSLCService.config().base_url.rstrip('/')+configuration_uri(identifier)
    payload={**record,'uri':root,'type':'oslc_config:Baseline','oslc_config:selections':{'uri':root+'/selections','type':'oslc_config:Selections','oslc_config:selects':[root+'/selections/'+str(index) for index in range(len(record['selections']['operations'])+1)]},
        'scope':'Frozen selections and native operation scopes; not a claim of full OSLC Config provider conformance'}
    context=request.headers.get('configuration-context')
    if context and context not in {configuration_uri(identifier),payload['uri']}:raise HTTPException(409,'Configuration-Context does not match this baseline')
    etag='W/"'+identifier+'"'
    if request.headers.get('if-none-match')==etag:return Response(status_code=304,headers={'ETag':etag,'Vary':'Accept, Authorization, Configuration-Context'})
    response=represent(payload,request);response.headers['ETag']=etag
    response.headers['Vary']='Accept, Authorization, Configuration-Context';return response


def summary(record):
    if record.get('kind')!='release-change':return None
    identifier=record.get('request_id')
    if not isinstance(identifier,str):return None
    order=record.get('order') or {};authorized=chain.valid_order(record)
    receipt=record.get('receipt') or {}
    completed=bool(record['state']=='completed' and authorized and receipt.get('configuration_id')==record['configuration_id'] and isinstance(receipt.get('operations'),list) and len(receipt['operations'])>=2 and all(item.get('receipt_verified') is True for item in receipt['operations']))
    return {'identifier':identifier,'record_key':'releases:'+identifier,'source_kind':'releases','category':'Source-to-release change',
        'owner_service':'oslc','title':record.get('title') or 'Source-to-release change',
        'request_number':record.get('request_number'),'order_number':order.get('order_number'),
        'reason':record.get('reason',''),'source_status':record['state'],
        'review_state':'Authorization retained' if authorized else {'submitted':'Request awaiting review','accepted':'Request accepted; execution not authorized'}.get(record['state'],record['state'].capitalize()),
        'execution_state':'Release receipts retained' if completed else 'Coordinated native operations' if authorized else 'Awaiting release authorization',
        'delivery_state':'Final catalog receipt retained' if completed else 'Not verified',
        'receipt_retained':completed,'authorization_kind':'Scoped release coordination' if authorized else 'Not recorded',
        'authorization_actor':order.get('authorized_by') if authorized else None,'policy_assessment':'Native owning-service policies remain authoritative',
        'updated_at':record.get('updated_at',''),'workspace':'#/change-control?record_source=releases&record='+quote(identifier,safe=''),
        'evidence':{'configuration_id':record['configuration_id'],'source_run_id':record['source_run_id']},'needs_attention':record['state'] in {'cancelled','rejected'},
        'read_only':True,'type':'oslc_cm:ChangeRequest','currentness':'Frozen release configuration; verify native receipts before closing'}


def dossier(record,uri):
    order=record.get('order') or {}
    return {'identifier':'releases:'+record['request_id'],'uri':uri+'#dossier','type':'urn:depo:change-control:NativeChangeDossier','read_only':True,
        'request':{'identifier':record['request_id'],'resource_type':'oslc_cm:ChangeRequest','state':record['state']},
        'baseline':{'status':'Frozen source-to-release selections','snapshot_digest':record['configuration_id'],'members':[],
            'currentness':'Exact source and native operation scopes; changes require a new reviewed release configuration',
            'configuration_conformance':'Configuration context and immutable baseline; not full OSLC Config provider conformance'},
        'release':{'state':record['state'],'authority':'Parent coordination never replaces native approval credentials','plan_digest':record['configuration_id'],
            'order':{'order_id':record['request_id'],'plan_digest':record['configuration_id'],'authorized_by':order.get('authorized_by'),'operation':'coordinate_source_to_release','publish':False} if chain.valid_order(record) else None,
            'execution_state':'Native operations retain their own receipts','delivery_state':'Verified' if record['state']=='completed' else 'Not verified'},
        'publication_receipt_retained':record['state']=='completed'}


@router.get('/oslc/change-control/configurations/{identifier}/selections',dependencies=[Depends(graph_read_identity)])
@router.get('/oslc/change-control/configurations/{identifier}/selections/{index}',dependencies=[Depends(graph_read_identity)])
def configuration_selection(identifier: str,request: Request,index: int | None=None):
    record=chain.registry().get('baseline:'+identifier)
    if not record or record.get('kind')!='release-baseline' or digest(record.get('selections'))!=identifier:raise HTTPException(404,'Frozen release configuration was not found')
    context=configuration_uri(identifier);root=OSLCService.config().base_url.rstrip('/')+context
    if request.headers.get('configuration-context') and request.headers['configuration-context'] not in {context,root}:raise HTTPException(409,'Configuration-Context does not match this baseline')
    members=[record['selections']['source'],*record['selections']['operations']]
    if index is None:payload={'uri':root+'/selections','type':'oslc_config:Selections','oslc_config:selects':[root+'/selections/'+str(position) for position in range(len(members))]}
    else:
        if not 0<=index<len(members):raise HTTPException(404,'Configuration selection was not found')
        item=members[index]
        canonical='/oslc/lifecycle/job-runs/'+quote(item['run_id'],safe='') if index==0 else '/oslc/change-control/records/'+item['source_kind']+'/'+quote(item['identifier'],safe='')
        payload={'uri':root+'/selections/'+str(index),'type':'oslc_config:VersionResource','dcterms:isVersionOf':OSLCService.config().base_url.rstrip('/')+canonical,
            'oslc_config:configuration':root,'snapshot':item,'configuration_id':identifier}
    response=represent(payload,request);response.headers['ETag']='W/"'+digest(payload)+'"';response.headers['Vary']='Accept, Authorization, Configuration-Context';return response


def contextual_selection(context,source,identifier,request):
    from urllib.parse import urlsplit
    path=urlsplit(context).path;prefix='/oslc/change-control/configurations/'
    if not path.startswith(prefix):raise HTTPException(409,'Choose a retained release configuration context')
    selected=path[len(prefix):]
    root=OSLCService.config().base_url.rstrip('/')+prefix+selected
    if context not in {prefix+selected,root}:raise HTTPException(409,'Configuration context must belong to this deployment')
    value=chain.registry().get('baseline:'+selected)
    if not value or digest(value.get('selections'))!=selected:raise HTTPException(409,'Release configuration was not found or its integrity failed')
    for index,item in enumerate(value['selections']['operations'],1):
        if item['source_kind']==source and item['identifier']==identifier:
            payload={'uri':root+'/selections/'+str(index),'type':'oslc_config:VersionResource','configuration_id':selected,'snapshot':item,
                'currentness':'Frozen operation scope; current native approval and execution evidence remains separate'}
            response=represent(payload,request);response.headers['ETag']='W/"'+digest(payload)+'"';response.headers['Vary']='Accept, Authorization, Configuration-Context';return response
    raise HTTPException(409,'The requested operation is outside this configuration')
