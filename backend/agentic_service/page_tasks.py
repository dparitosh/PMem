"""Page-local views over existing owned task stores; no second execution engine."""
import asyncio
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Query
from backend.depo_platform.authorization import graph_read_identity
from . import sessions

PAGES = {'home','import','ontology','data-flow','catalog','data-products','registry','graph','code-audit','modeling','requirements','qif','whereused','data-quality','quality','reports','admin'}
ALIASES = {'data-catalog':'catalog','recommendations':'quality'}
router = APIRouter(prefix='/api/v1/page-tasks',tags=['page-tasks'])


def page_binding(owner, context):
    if not context:
        return {}
    if not isinstance(context,dict): raise HTTPException(422,'Invalid task page context')
    raw=context.get('page')
    if not isinstance(raw,str): raise HTTPException(422,'Unknown task page')
    page=ALIASES.get(raw,raw)
    if not isinstance(page,str) or page not in PAGES: raise HTTPException(422,'Unknown task page')
    selected={}
    for key in ('ontology_id','ontology_prefix','import_task_id','product_id','run_id','node_id'):
        value=context.get(key)
        if value is not None:
            if not isinstance(value,str) or len(value)>256: raise HTTPException(422,'Invalid task selection')
            selected[key]=value
    return {'page_context':{'page':page,**selected},'page_owner':hashlib.sha256((owner+':'+page).encode()).hexdigest()}


def stores():
    from . import goal_routes, router as routes
    return {'goal':goal_routes.store,'workflow':routes.workflow_store,'tool':routes.telemetry.store}


def summary(record,kind):
    return {'run_id':record['run_id'],'kind':kind,'status':record.get('status','unknown'),
            'title':record.get('goal') or record.get('workflow_id') or record.get('task_label') or 'Reviewed tool action',
            'agent_id':record.get('agent_id'),'page_context':record.get('page_context',{}),
            'updated_at':record.get('updated_at') or record.get('finished_at') or record.get('started_at') or record.get('created_at'),
            'state_source':'retained_record'}


@router.get('')
async def list_tasks(request:Request,page:str,limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0)):
    owner=sessions.owner(request,graph_read_identity(request))
    binding=page_binding(owner,{'page':page})
    async def read(kind,store):
        total,rows=await asyncio.to_thread(store.page,limit=limit,offset=offset,field='page_owner',value=binding['page_owner'])
        return kind,total,[summary(r,kind) for r in rows if r.get('owner')==owner and r.get('page_owner')==binding['page_owner']]
    try: batches=await asyncio.gather(*(read(k,s) for k,s in stores().items()))
    except Exception as exc: raise HTTPException(503,'Task history unavailable; existing executions are retained') from exc
    rows=sorted([r for _,_,items in batches for r in items],key=lambda r:(r.get('updated_at') or '',r['run_id']),reverse=True)
    return {'tasks':rows,'page':binding['page_context']['page'],'offset':offset,'limit_per_kind':limit,
            'has_more':any(offset+limit<total for _,total,_ in batches)}


@router.get('/{kind}/{run_id}')
async def task_detail(kind:str,run_id:str,request:Request):
    owner=sessions.owner(request,graph_read_identity(request))
    store=stores().get(kind)
    if store is None: raise HTTPException(422,'Unsupported task kind')
    try: record=await asyncio.to_thread(store.get,run_id)
    except Exception as exc: raise HTTPException(503,'Task status unavailable; execution was not resubmitted') from exc
    if not record: raise HTTPException(404,'Task not found')
    if record.get('owner')!=owner: raise HTTPException(403,'Task belongs to another identity')
    if kind=='goal':
        from .goal_routes import goal_status
        return await goal_status(run_id,request)
    if kind=='workflow':
        from .router import workflow_run
        return await asyncio.to_thread(workflow_run,run_id,request)
    allowed={'run_id','status','task_label','agent_id','page_context','operation','workflow_id',
             'started_at','finished_at','updated_at','created_at','deadline_at','duration_ms',
             'evidence_count','error_type'}
    public={key:value for key,value in record.items() if key in allowed}
    span_fields={'tool_id','attempt','status','duration_ms','error_type'}
    public['tool_spans']=[{k:v for k,v in span.items() if k in span_fields}
                          for span in record.get('tool_spans',[]) if isinstance(span,dict)]
    if public.get('status')=='running' and public.get('deadline_at'):
        try:
            if datetime.now(timezone.utc)>=datetime.fromisoformat(public['deadline_at']):
                public.update(status='interrupted',error_type='ExecutionDeadlineElapsed',state_source='deadline_projection')
        except (TypeError,ValueError):
            public.update(status='interrupted',error_type='InvalidExecutionDeadline',state_source='deadline_projection')
    return public
