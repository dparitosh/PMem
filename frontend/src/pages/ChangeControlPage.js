import ApprovalMatrixSettings from '../Components/ApprovalMatrixSettings';
import WorkflowDefinitionActions from '../Components/WorkflowDefinitionActions';
import PipelinePublicationRequest from '../Components/PipelinePublicationRequest';
import { businessText } from '../utils/businessText';
import React, {useEffect,useRef,useState} from 'react';
import {apiClient} from '../services/apiClient';
import {buildSemanticServiceUrl} from '../config';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import './ChangeControlPage.css';
import ChangeDossier from '../Components/ChangeDossier';
import ReleaseChangePanel from '../Components/ReleaseChangePanel';
import NativeChangeActions from '../Components/NativeChangeActions';

const SOURCES=[['all','All workspaces'],['releases','Source-to-release changes'],['merges','Ontology merges'],['bridges','Instance mappings'],['publications','Ontology publications'],['definitions','Workflow definitions'],['workflow_changes','Workflow maintenance changes'],['import_changes','Engineering record loads'],['pipeline','Data Flow runs'],['product_changes','Product release requests'],['products','Published product records'],['learning','Learning reviews']];
const VIEWS=[['requests','Change requests'],['orders','Change orders'],['workflows','Workflow records']];
const hasRetainedAuthorization=row=>['Service authorization','Scoped release coordination','Delegated policy'].includes(row.authorization_kind)&&typeof row.authorization_actor==='string'&&Boolean(row.authorization_actor.trim());
const isRequest=row=>row.type==='oslc_cm:ChangeRequest'||Boolean(row.request_number);
const displayDate=value=>{const date=new Date(value);return Number.isNaN(date.getTime())?'Date unavailable':date.toLocaleString();};
const publicationState=row=>row.receipt_retained?'Published':row.change_state==='needs_recovery'?'Verification needed':['submitted','accepted','authorized'].includes(row.change_state)?'Awaiting publication':row.delivery_state;
const readSelection=()=>{
 const params=new URLSearchParams(window.location.hash.split('?')[1]||'');
 const known=value=>SOURCES.some(([id])=>id===value);
 const source=known(params.get('source')) ? params.get('source') : 'all';
 const recordSource=params.get('record_source') || source;
 const value=Number(params.get('offset')||0);
 const returnTo=params.get('return_to')||'';
 return {returnTo:returnTo.startsWith('#/ontology?')?returnTo:'',source,recordSource:known(recordSource)&&recordSource!=='all'?recordSource:null,
  view:VIEWS.some(([id])=>id===params.get('view'))?params.get('view'):'requests',
  record:params.get('record')||'',offset:Number.isInteger(value)&&value>=0&&value<=100000&&value%25===0?value:0};
};
const navigate=patch=>{
 const params=new URLSearchParams(window.location.hash.split('?')[1]||'');
 Object.entries(patch).forEach(([key,value])=>{if(value==null||value==='')params.delete(key);else params.set(key,String(value));});
 const hash='#/change-control'+(params.size?'?'+params.toString():'');
 if(window.location.hash!==hash){window.history.pushState(null,'',hash);window.dispatchEvent(new HashChangeEvent('hashchange'));}
};
export default function ChangeControlPage(){
 const [routeSelection,setRouteSelection]=useState(readSelection);
 useEffect(()=>{const changed=()=>setRouteSelection(readSelection());window.addEventListener('hashchange',changed);window.addEventListener('popstate',changed);return()=>{window.removeEventListener('hashchange',changed);window.removeEventListener('popstate',changed);};},[]);
 const {source,offset,view,record:recordId,recordSource,returnTo}=routeSelection;
 const [query,setQuery]=useState(''),[revision,setRevision]=useState(0);
 const [state,setState]=useState({loading:true,records:[],coverage:[],error:''});
 const [selectionError,setSelectionError]=useState('');
 const [detail,setDetail]=useState(null),[detailPending,setDetailPending]=useState(false);
 const request=useRef(null),detailRequest=useRef(null);
 const expectedKey=recordSource&&recordId?`${recordSource}:${recordId}`:null;
 const selected=detail?.record_key===expectedKey?detail:null;
 const detailLoading=Boolean(expectedKey&&detailPending);
 const openChange=row=>navigate({record:row.identifier,record_source:row.source_kind||row.record_key.split(':')[0]});
 const closeDetails=()=>{detailRequest.current?.abort();setDetailPending(false);setDetail(null);navigate({record:null,record_source:null});};
 useEffect(()=>{
  const invalidate=()=>{request.current?.abort();detailRequest.current?.abort();setDetailPending(false);setDetail(null);setSelectionError('');setState({loading:true,records:[],coverage:[],error:''});setRevision(value=>value+1);};
  const refresh=()=>setRevision(value=>value+1);
  const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];
  events.forEach(name=>window.addEventListener(name,invalidate));window.addEventListener('depo:access-verified',refresh);
  return()=>{events.forEach(name=>window.removeEventListener(name,invalidate));window.removeEventListener('depo:access-verified',refresh);};
 },[]);
 useEffect(()=>{
  const controller=new AbortController();request.current=controller;
  setState({loading:true,records:[],coverage:[],error:''});
  apiClient.get(buildSemanticServiceUrl('oslc','/api/v1/change-control/records'),{signal:controller.signal,timeout:30000,params:{source,limit:25,offset}}).then(response=>{
   const data=response.data;if(!Array.isArray(data?.records)||!Array.isArray(data?.coverage)||data.records.some(row=>!row||typeof row.record_key!=='string'||typeof row.identifier!=='string'||typeof row.review_state!=='string'||typeof row.execution_state!=='string'||typeof row.delivery_state!=='string')||data.coverage.some(row=>!row||typeof row.source!=='string'||typeof row.status!=='string'))throw new Error('Invalid change evidence response');
   if(!controller.signal.aborted)setState({...data,loading:false,error:''});
  }).catch(error=>{if(!controller.signal.aborted)setState({loading:false,records:[],coverage:[],error:apiErrorMessage(error,'Change evidence could not be loaded. No decision state was verified.')});});
  return()=>{controller.abort();if(request.current===controller)request.current=null;};
 },[source,revision,offset]);
 useEffect(()=>{
  setDetail(null);setSelectionError('');setDetailPending(Boolean(expectedKey));
  if(!expectedKey)return;
  const controller=new AbortController();detailRequest.current=controller;
  apiClient.get(buildSemanticServiceUrl('oslc',`/api/v1/change-control/records/${encodeURIComponent(recordSource)}/${encodeURIComponent(recordId)}`),{signal:controller.signal,timeout:15000}).then(({data})=>{
   if(controller.signal.aborted)return;
   if(data?.record_key!==expectedKey||data.identifier!==recordId||['review_state','execution_state','delivery_state'].some(key=>typeof data[key]!=='string'))throw new Error('Selected evidence identity or contract mismatch');
   setDetail(data);
  }).catch(error=>{if(!controller.signal.aborted)setSelectionError(apiErrorMessage(error,'Detailed change dossier could not be loaded. No decision state was verified.'));})
   .finally(()=>{if(!controller.signal.aborted)setDetailPending(false);});
  return()=>{controller.abort();if(detailRequest.current===controller)detailRequest.current=null;};
 },[expectedKey,recordId,recordSource,revision]);
 const rows=state.records.filter(row=>view==='orders'?Boolean(row.order_number):view==='workflows'?!isRequest(row):isRequest(row)).filter(row=>[row.title,row.reference,row.request_number,row.order_number,row.subject,row.identifier,row.category,row.review_state,row.execution_state,row.delivery_state].some(value=>String(value||'').toLowerCase().includes(query.toLowerCase())));
 return <section className="change-control" aria-label="Change Control workspace">
  {returnTo && <nav aria-label="Mapping review navigation"><a href={returnTo}>← Return to mapping review</a></nav>}
  <header className="change-control__header"><div><h2>Change Control</h2></div><button className="depo-button depo-button--secondary" disabled={state.loading} onClick={()=>setRevision(value=>value+1)}>Refresh changes</button></header>
  <ol className="change-control__journey"><li>Prepare proposal</li><li>Review evidence</li><li>Authorize exact scope</li><li>Execute</li><li>Verify delivery</li></ol>
  <p className="change-control__scope">Approval, execution and delivery are tracked separately.</p>
  <ApprovalMatrixSettings/>
  <ReleaseChangePanel records={state.records} loading={state.loading} onCreated={value=>{navigate({record:value.request_id,record_source:'releases'});setRevision(current=>current+1);}}/>
  <div className="change-control__metrics" aria-label="Loaded change evidence summary"><div><strong>{state.loading||state.error?'—':state.records.length}</strong><span>Loaded records</span></div><div><strong>{state.loading||state.error?'—':state.records.filter(hasRetainedAuthorization).length}</strong><span>Authorizations retained</span></div><div><strong>{state.loading||state.error?'—':state.records.filter(row=>row.needs_attention).length}</strong><span>Need attention</span></div><div><strong>{state.loading||state.error?'—':state.records.filter(row=>row.receipt_retained).length}</strong><span>Publication receipts retained</span></div></div>
  <nav className="change-control__views" aria-label="Change registers">{VIEWS.map(([id,label])=><button key={id} aria-pressed={view===id} onClick={()=>navigate({view:id,offset:null,record:null,record_source:null})}>{label}</button>)}</nav>
  <div className="change-control__toolbar"><label>Workspace<select value={source} onChange={event=>navigate({source:event.target.value,view:event.target.value==='definitions'?'workflows':view,record:null,record_source:null,offset:null})}>{SOURCES.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label><label>Find in loaded records<input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Name, identifier or state"/></label></div>
  {state.loading&&<p role="status">Loading retained change evidence…</p>}
  {state.error&&<p role="alert">{state.error}</p>}{selectionError&&<p role="alert">{selectionError}</p>}
  {state.partial&&<p role="alert">Partial evidence: {state.coverage.filter(row=>row.status!=='available').map(row=>row.source).join(', ')} could not be read. Missing evidence does not mean no approvals exist.</p>}
  {!state.loading&&!state.error&&<><p className="change-control__scope">{rows.length} {view==='orders'?'change orders':view==='workflows'?'workflow records':'change requests'} in loaded history</p><div className="change-control__table"><table><thead><tr><th scope="col">Change / source</th><th scope="col">CR number</th><th scope="col">CO number</th><th scope="col">Review</th><th scope="col">Execution</th><th scope="col">Publication</th><th scope="col">Action</th></tr></thead><tbody>{rows.map(row=><tr key={row.record_key}><td><strong>{businessText(row.title)}</strong><small>{row.category}{row.reference ? ` · ${row.reference}` : ''}</small><small>{displayDate(row.updated_at)}</small></td><td className="change-control__reference">{row.request_number||(isRequest(row)?'Legacy request':'Not requested')}</td><td className="change-control__reference">{row.order_number||'Not issued'}</td><td>{row.review_state}<small>{row.authorization_actor||row.requested_by||''}</small></td><td><span className={row.needs_attention?'change-control__attention':''}>{row.execution_state}</span></td><td>{publicationState(row)}</td><td><button onClick={()=>openChange(row)} aria-label={`View ${row.source_kind==='definitions'?'definition':'change'} ${row.request_number||businessText(row.title)}`}>{row.source_kind==='definitions'?'View definition':'View change'}</button></td></tr>)}{!rows.length&&<tr><td colSpan={7}>No {view==='orders'?'change orders':view==='workflows'?'workflow records':'change requests'} match this view.</td></tr>}</tbody></table></div><nav className="change-control__toolbar" aria-label="Change history pages"><button disabled={offset===0} onClick={()=>navigate({offset:Math.max(0,offset-25)})}>Previous history</button><button disabled={!state.has_more} onClick={()=>navigate({offset:offset+25})}>Next history</button></nav></>}
  {detailLoading&&<p role="status">Loading exact change dossier…</p>}
  {selected&&<section className="change-control__detail" aria-label="Selected change evidence"><header><h3>{selected.request_number&&<span className="change-control__reference">{selected.request_number} · </span>}{businessText(selected.title)}</h3><button onClick={closeDetails}>Close details</button></header><p>{selected.category}{selected.order_number&&` · ${selected.order_number}`}</p>{selected.reason&&<p>{businessText(selected.reason)}</p>}{!detailLoading&&<>{selected.source_kind==='definitions'?<><WorkflowDefinitionActions key={selected.record_key} jobId={selected.evidence?.job_id} version={selected.evidence?.version} onChanged={data=>{navigate({source:'workflow_changes',view:'requests',record_source:'workflow_changes',record:data.preview_id});setRevision(value=>value+1);}}/><dl><dt>Workflow</dt><dd>{selected.reference||selected.title}</dd><dt>Version</dt><dd>{selected.evidence?.version}</dd><dt>Owner</dt><dd>{selected.evidence?.owner||'Not recorded'}</dd><dt>Approval</dt><dd>{selected.review_state}</dd><dt>Availability</dt><dd>{selected.execution_state}</dd></dl></>:<ChangeDossier dossier={selected.dossier}/>}{selected.source_kind==='import_changes'&&<NativeChangeActions key={selected.record_key} kind="import_changes" previewId={selected.identifier} onChanged={()=>setRevision(value=>value+1)}/>} {selected.source_kind==='workflow_changes'&&<NativeChangeActions key={selected.record_key} kind="workflow_changes" previewId={selected.identifier} onChanged={()=>setRevision(value=>value+1)}/>} {selected.source_kind==='releases'&&<ReleaseChangePanel requestId={selected.identifier} onChanged={()=>setRevision(value=>value+1)}/>}{selected.record_key.startsWith('publications:')&&<NativeChangeActions key={selected.record_key} kind="publications" previewId={selected.identifier} onChanged={()=>setRevision(value=>value+1)}/>} {selected.record_key.startsWith('pipeline:')&&selected.type!=='oslc_cm:ChangeRequest'&&!selected.receipt_retained&&selected.source_status==='completed'&&['normalize-ceim','validate-semantic-batch','normalize-unstructured-ceim','connector-ceim-normalize'].includes(selected.evidence?.job_type)&&<PipelinePublicationRequest key={selected.record_key} runId={selected.identifier} sourceSystem={selected.evidence?.source_system||''} onCreated={()=>{navigate({view:'requests'});setRevision(value=>value+1);}}/>} {selected.record_key.startsWith('pipeline:')&&selected.type==='oslc_cm:ChangeRequest'&&<NativeChangeActions key={selected.record_key} kind="pipeline" previewId={selected.identifier} onChanged={()=>setRevision(value=>value+1)}/>} {selected.record_key.startsWith('product_changes:')&&<NativeChangeActions key={selected.record_key} kind="product_changes" previewId={selected.identifier} onChanged={()=>setRevision(value=>value+1)}/>}{selected.record_key.startsWith('merges:')&&<NativeChangeActions key={selected.record_key} previewId={selected.identifier} onChanged={()=>setRevision(value=>value+1)}/>} {selected.record_key.startsWith('bridges:')&&String(selected.evidence?.preview_id||selected.identifier).startsWith('bridge-preview-')&&<NativeChangeActions key={selected.record_key} kind="bridges" previewId={selected.evidence?.preview_id||selected.identifier} onChanged={data=>{if(data.publication_id!==selected.identifier)navigate({record:data.publication_id,record_source:'bridges'});setRevision(value=>value+1);}}/>}</>}<details><summary>Governance evidence</summary><dl><dt>Owning service</dt><dd>{selected.owner_service}</dd><dt>Authorization scope</dt><dd>{selected.authorization_kind} · {selected.authorization_actor||'No actor recorded'}</dd><dt>Policy checks</dt><dd>{businessText(selected.policy_assessment)} (not approval)</dd><dt>Review</dt><dd>{selected.review_state}</dd><dt>Execution</dt><dd>{selected.execution_state}</dd><dt>Delivery</dt><dd>{selected.delivery_state}</dd></dl><p>{businessText(selected.currentness)}</p></details><details><summary>Retained identifiers and digests</summary><dl>{Object.entries(selected.evidence||{}).map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd>{value}</dd></React.Fragment>)}</dl></details><a href={typeof selected.workspace==='string'&&selected.workspace.startsWith('#/')?selected.workspace:'#/change-control'}>{selected.source_kind==='definitions'?'Review workflow definition':'Open owning workflow'}</a></section>}
 </section>;
}
