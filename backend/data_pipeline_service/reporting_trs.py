"""Bounded TRS consumer for the existing leased pipeline worker."""
import copy,json,time,uuid
from urllib.parse import urlsplit,parse_qs,unquote
from backend.depo_platform.execution_guard import ensure_execution_allowed
from . import reporting_store as store


class LocalProvider:
    """This deployment's OSLC provider; never follows a caller-supplied URL."""
    def base(self,cursor=None):
        from backend.Services.oslc_trs_service import OSLCTRSService
        if not OSLCTRSService.is_enabled():raise RuntimeError('TRS provider is disabled')
        return OSLCTRSService.base_resources(limit=1000,**(cursor or {}))

    def changes(self,after):
        from backend.Services.oslc_trs_service import OSLCTRSService
        if not OSLCTRSService.is_enabled():raise RuntimeError('TRS provider is disabled')
        return OSLCTRSService.change_log(after=after,limit=100)

    def resource(self,uri,definition):
        from backend.Services.oslc_service import OSLCService
        parsed=urlsplit(uri);prefix='/oslc/resources/'
        ids=parse_qs(parsed.query).get('ontology_id',[])
        # Exact version scope excludes unversioned legacy records and control resources.
        if not parsed.path.startswith(prefix) or len(ids)!=1 or ids[0] not in definition['ontology_ids']:return None
        value=OSLCService.get_resource(unquote(parsed.path[len(prefix):]),ontology_id=ids[0])
        if value is None:raise RuntimeError('Changed resource is unavailable; checkpoint was not advanced')
        return store.normalise(uri,json.loads(json.dumps(value,default=str,allow_nan=False)),definition)


def next_cursor(link):
    if not link:return None
    parsed=urlsplit(link);values=parse_qs(parsed.query)
    if parsed.path!='/oslc/trs/base':raise ValueError('Invalid local TRS Base continuation')
    identifier=values.get('snapshot_id',[''])[0];offset=int(values.get('offset',['0'])[0])
    uuid.UUID(identifier)
    if offset<0:raise ValueError('Invalid TRS Base offset')
    return {'snapshot_id':identifier,'offset':offset}


def begin(state,reason):
    return {**state,'phase':'base','building_generation':uuid.uuid4().hex,'members':[],
            'base_cursor':None,'next_cursor':None,'base_started':False,'member_offset':0,
            'base_cutoff':None,'freshness':'refreshing','rebase_reason':reason,'last_error':None}


def _base_step(identifier,state,definition,provider,deadline):
    expected=copy.deepcopy(state)
    if not state.get('members'):
        if state.get('base_started') and state.get('base_cursor') is None:
            updated={**state,'phase':'events','trs_after':state['base_cutoff'],'freshness':'awaiting_change_check',
                     'last_refreshed_at':store.now(),'last_error':None}
            return store.commit(identifier,expected,updated,[],promote=True)
        try:
            page=provider.base(state.get('base_cursor'))
        except RuntimeError as exc:
            recoverable = str(exc) in {
                'TRS Base snapshot expired or missing; restart from /oslc/trs/base',
                'TRS snapshot page missing; restart from /oslc/trs/base',
                'TRS snapshot page is incomplete; rebase required',
            }
            if not recoverable or not state.get('base_cursor'):raise
            return store.commit(identifier,expected,begin(state,'Base snapshot expired; rebuilding reporting selection'),[])
        members=page.get('members');cutoff=page.get('cutoff_order')
        if not isinstance(members,list) or len(members)>1000 or type(cutoff) is not int or cutoff<0:
            raise ValueError('Invalid TRS Base page')
        if state.get('base_cutoff') is not None and state['base_cutoff']!=cutoff:raise ValueError('TRS Base cutoff changed within a snapshot')
        updated={**state,'base_started':True,'base_cutoff':cutoff,'members':[m['resource_uri'] for m in members],
                 'member_offset':0,'next_cursor':next_cursor(page.get('nextPage'))}
        if not members:updated['base_cursor']=updated['next_cursor']
        return store.commit(identifier,expected,updated,[])
    changes=[];position=state.get('member_offset',0)
    while position<len(state['members']) and len(changes)<50 and time.monotonic()<deadline:
        ensure_execution_allowed();uri=state['members'][position]
        resource=provider.resource(uri,definition)
        if resource is not None:changes.append((uri,resource))
        position+=1
    updated={**state,'member_offset':position}
    if position==len(state['members']):updated.update(members=[],member_offset=0,base_cursor=state['next_cursor'])
    return store.commit(identifier,expected,updated,changes)


def _events_step(identifier,state,definition,provider,deadline):
    expected=copy.deepcopy(state);after=state.get('trs_after',0);page=provider.changes(after)
    events=page.get('events');head=page.get('head_order')
    if not isinstance(events,list) or len(events)>100 or type(head) is not int:raise ValueError('Invalid TRS changelog')
    if page.get('rebase_required') or head<after:
        return store.commit(identifier,expected,begin(state,'TRS retention gap or provider reset'),[])
    if not events and head>after:raise ValueError('TRS changelog did not supply its pending events')
    changes=[];order=after
    for event in events:
        if time.monotonic()>=deadline:break
        ensure_execution_allowed()
        number=event.get('order');uri=event.get('resource_uri');kind=event.get('event_type')
        if type(number) is not int or number<=order or not isinstance(uri,str) or kind not in {'Creation','Modification','Deletion'}:
            raise ValueError('Invalid or unordered TRS change event')
        path=unquote(urlsplit(uri).path)
        # Ontology publication notifications invalidate the selected scope as a whole.
        if path=='/oslc/trs/base' or path.startswith('/oslc/shapes/') and path.rsplit('/',1)[-1] in definition['ontology_ids']:
            return store.commit(identifier,expected,begin(state,'Selected ontology publication changed'),[])
        changes.append((uri,None if kind=='Deletion' else provider.resource(uri,definition)))
        order=number
    pending=order<head
    updated={**state,'trs_after':order,'last_assessed_at':store.now(),'last_error':None,
             'freshness':'changes_pending' if pending else 'tracked_feed_caught_up',
             'last_refreshed_at':store.now() if changes else state.get('last_refreshed_at')}
    return store.commit(identifier,expected,updated,changes)


def synchronize(payload,provider=None):
    identifier=payload.get('feed_id','')
    provider=provider or LocalProvider()
    budget=payload.get('budget_seconds',45);steps=payload.get('max_steps',30)
    if type(budget) is not int or not 5<=budget<=120 or type(steps) is not int or not 1<=steps<=200:
        raise ValueError('Choose a 5–120 second refresh budget and 1–200 bounded steps')
    with store.registry().advisory_lock('reporting:'+identifier) as acquired:
        if not acquired:raise RuntimeError('This reporting dataset is already refreshing')
        feed=store.get(identifier)
        if feed['status']!='approved':raise ValueError('Approve the reporting selection before replication')
        definition=store.validate_definition(feed['definition']);state=feed['state'];deadline=time.monotonic()+budget
        if not state:
            state=store.commit(identifier,{},begin({},'Initial replication'),[])
        for _ in range(steps):
            if time.monotonic()>=deadline:break
            ensure_execution_allowed()
            if state['phase']=='base':state=_base_step(identifier,state,definition,provider,deadline)
            else:
                state=_events_step(identifier,state,definition,provider,deadline)
                if state['phase']=='events' and state['freshness']=='tracked_feed_caught_up':break
        return {'status':'completed','job_type':'trs-reporting-sync','feed_id':identifier,
                'replication_state':state['phase'],'freshness':state.get('freshness'),
                'checkpoint':state.get('trs_after'),'generation':state.get('active_generation'),
                'scope':'Selected exact ontology versions and tracked events; publisher coverage remains partial.',
                'graph_publication_performed':False,'product_publication_performed':False}


def execute(runner,payload,*,correlation_id):
    started=store.now()
    try:return {**synchronize(payload),'correlation_id':correlation_id}
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('Reporting replication failed feed_id=%s correlation_id=%s',payload.get('feed_id'),correlation_id)
        try:
            ensure_execution_allowed();store.record_failure(payload.get('feed_id'),type(exc).__name__,started)
        except Exception:logging.getLogger(__name__).warning('Reporting failure status could not be retained')
        raise
