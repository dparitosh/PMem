"""Read-only Semantica projections of already-authorized retained evidence."""
from datetime import datetime
import hashlib
import json
import math
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from semantica.context import ContextGraph, DecisionRecorder
from semantica.context.decision_models import Decision
from semantica.provenance import ProvenanceManager
from semantica.provenance.storage import InMemoryStorage
from backend.depo_platform.authorization import graph_read_identity
from backend.depo_platform.peer_http import async_peer_response
from backend.depo_platform.network import gateway_subscription_headers
from backend.depo_platform.service_urls import service_url

router=APIRouter(prefix='/api/v1/ontologies/evidence-dossiers',tags=['Evidence dossiers'],dependencies=[Depends(graph_read_identity)])
KINDS={'merges','bridges','publications','pipeline','products','learning','decisions'}


def project(record):
    """No global memory, database writes, model calls or new approval authority."""
    graph=ContextGraph()
    provenance=ProvenanceManager(storage=InMemoryStorage())
    root=record['uri']
    snapshot=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    graph.add_node(root,'EvidenceRecord',record.get('title','Retained evidence'))
    provenance.track_entity(root,source=root,metadata={'snapshot_sha256':snapshot,'scope':'read_projection'})
    sources=[]
    for field,value in list(record.get('evidence',{}).items())[:24]:
        node_id=root+'#'+quote(field,safe='')
        graph.add_node(node_id,'SourceReference',str(value),field=field)
        graph.add_edge(root,node_id,'HAS_EVIDENCE')
        provenance.track_entity(node_id,source=root,metadata={'field':field,'value':str(value)},parent_entity_id=root)
        entry=provenance.get_provenance(node_id) or {}
        sources.append({'field':field,'value':str(value),'source_uri':root,'checksum':entry.get('checksum')})
    decisions=[]
    recorder=DecisionRecorder(graph_store=graph)
    for index,item in enumerate(record.get('decision_observations',[])[:25]):
        timestamp=None
        if item.get('timestamp'):
            try:
                parsed=datetime.fromisoformat(item['timestamp'])
                if parsed.tzinfo is not None:timestamp=parsed
            except ValueError:pass
        confidence=item.get('confidence')
        calibrated=type(confidence) in {int,float} and math.isfinite(confidence) and 0<=confidence<=1 and item.get('confidence_basis')=='calibrated'
        node_id=root+f'#decision-{index}'
        decision=Decision(decision_id=node_id,category='retained_assessment',scenario=item.get('scenario') or record['title'],
            reasoning=item.get('reasoning') or 'No recorded explanation',outcome=item.get('outcome') or 'not_recorded',
            confidence=confidence if calibrated else 0,timestamp=timestamp,decision_maker=item.get('decision_maker') or 'not_recorded',
            metadata={'confidence_status':'calibrated' if calibrated else 'not_established'})
        recorder.record_decision(decision,entities=[],source_documents=[])
        graph.add_edge(node_id,root,'ASSESSES')
        decisions.append({**item,'id':node_id,'confidence':confidence if calibrated else None,'timestamp':timestamp.isoformat() if timestamp else None})
    data=graph.to_dict()
    for node in data['nodes']:
        if node['type']=='Decision' and node.get('properties',{}).get('confidence_status')!='calibrated':
            node['properties']['confidence']=None
    return {'schema_version':1,'engine':'Semantica','components':['ContextGraph','DecisionRecorder','ProvenanceManager'],
        'record_key':record['record_key'],'source_snapshot':{key:record.get(key) for key in ('source_status','updated_at','review_state','execution_state','delivery_state')},'snapshot_sha256':snapshot,'graph':data,'decisions':decisions,
        'decision_count':record.get('decision_count'),'decisions_truncated':record.get('decisions_truncated',False),
        'provenance':sources,'provenance_turtle':provenance.export_prov(),
        'scope':'Selected retained record only; relationships are explicit evidence references, not inferred causality.',
        'persistence':'Rebuilt from retained PostgreSQL evidence; no second audit store.',
        'integrity_scope':'Checksums bind this projection; original source integrity is not independently verified.',
        'authorization':'Read-only evidence; existing review and execution controls remain required.'}


@router.get('/{source}/{identifier:path}')
async def dossier(source:str,identifier:str,request:Request):
    if source not in KINDS or not identifier or len(identifier)>300:
        raise HTTPException(422,'Invalid evidence reference')
    base=service_url('OSLC_SERVICE_URL','http://127.0.0.1:8015/api/v1')
    if not base.endswith('/api/v1'):base+='/api/v1'
    endpoint=base+'/change-control/records/'+source+'/'+quote(identifier,safe='')
    # Forward the caller credential, never substitute broader service authority
    # or trust caller-supplied principal/role headers at the receiving service.
    headers={key:request.headers[key] for key in ('authorization','x-api-key') if request.headers.get(key)}
    if not headers:raise HTTPException(403,'A delegated read credential is required')
    headers={**gateway_subscription_headers(endpoint),**headers,'Accept':'application/json'}
    try:
        response=await async_peer_response('GET',endpoint,headers=headers,budget=15,response_limit=65536)
        if response.status_code in {401,403,404}:raise HTTPException(response.status_code,'Evidence is unavailable to this identity')
        if response.status_code!=200:raise HTTPException(503,'Retained evidence service is unavailable')
        record=response.json()
        if not isinstance(record,dict) or record.get('record_key')!=source+':'+identifier or record.get('source_kind')!=source or not isinstance(record.get('uri'),str):
            raise ValueError('Evidence identity mismatch')
        return await run_in_threadpool(project,record)
    except HTTPException:raise
    except (httpx.HTTPError,TimeoutError,ValueError,RuntimeError,TypeError,KeyError) as failure:
        raise HTTPException(503,'Dossier context is unavailable; no new decision or write was performed') from failure
