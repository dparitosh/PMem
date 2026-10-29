import React, {useEffect,useRef,useState} from 'react';
import {apiClient} from '../services/apiClient';
import {buildSemanticServiceUrl} from '../config';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import './ChangeControlPage.css';

const SOURCES=[['all','All workspaces'],['merges','Ontology merges'],['bridges','Instance mappings'],['publications','Ontology publications'],['pipeline','Data Flow runs'],['products','Product releases'],['learning','Learning reviews']];
export default function ChangeControlPage(){
 const [source,setSource]=useState('all'),[query,setQuery]=useState(''),[revision,setRevision]=useState(0);
 const [state,setState]=useState({loading:true,records:[],coverage:[],error:''});
 const [offset,setOffset]=useState(0);
 const [selected,setSelected]=useState(null);const request=useRef(null);
 useEffect(()=>{
  const invalidate=()=>{request.current?.abort();setSelected(null);setState({loading:true,records:[],coverage:[],error:''});setRevision(value=>value+1);};
  const refresh=()=>setRevision(value=>value+1);
  const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];
  events.forEach(name=>window.addEventListener(name,invalidate));window.addEventListener('depo:access-verified',refresh);
  return()=>{events.forEach(name=>window.removeEventListener(name,invalidate));window.removeEventListener('depo:access-verified',refresh);};
 },[]);
 useEffect(()=>{
  const controller=new AbortController();request.current=controller;
  setSelected(null);setState({loading:true,records:[],coverage:[],error:''});
  apiClient.get(buildSemanticServiceUrl('oslc','/api/v1/change-control/records'),{signal:controller.signal,timeout:30000,params:{source,limit:25,offset}}).then(response=>{
   const data=response.data;if(!Array.isArray(data?.records)||!Array.isArray(data?.coverage)||data.records.some(row=>!row||typeof row.record_key!=='string'||typeof row.review_state!=='string'||typeof row.execution_state!=='string'||typeof row.delivery_state!=='string')||data.coverage.some(row=>!row||typeof row.source!=='string'||typeof row.status!=='string'))throw new Error('Invalid change evidence response');
   if(!controller.signal.aborted)setState({...data,loading:false,error:''});
  }).catch(error=>{if(!controller.signal.aborted)setState({loading:false,records:[],coverage:[],error:apiErrorMessage(error,'Change evidence could not be loaded. No decision state was verified.')});});
  return()=>{controller.abort();if(request.current===controller)request.current=null;};
 },[source,revision,offset]);
 const rows=state.records.filter(row=>[row.title,row.identifier,row.category,row.review_state,row.execution_state,row.delivery_state].some(value=>String(value||'').toLowerCase().includes(query.toLowerCase())));
 return <section className="change-control" aria-label="Change Control workspace">
  <header className="change-control__header"><div><span className="change-control__eyebrow">End-to-end change visibility</span><h2>Change Control</h2><p>Find retained proposals, authorization evidence, execution progress and delivery across workspaces.</p></div><button className="depo-button depo-button--secondary" disabled={state.loading} onClick={()=>setRevision(value=>value+1)}>Refresh changes</button></header>
  <ol className="change-control__journey"><li>Prepare proposal</li><li>Review evidence</li><li>Authorize exact scope</li><li>Execute</li><li>Verify delivery</li></ol>
  <p className="change-control__scope">Central visibility is read-only in this phase. Review and execution remain in the owning workflow. A completed run or passed policy check is not end-to-end approval.</p>
  <div className="change-control__metrics" aria-label="Loaded change evidence summary"><div><strong>{state.loading||state.error?'—':state.records.length}</strong><span>Loaded records</span></div><div><strong>{state.loading||state.error?'—':state.records.filter(row=>row.review_state==='Authorization retained').length}</strong><span>Service authorization retained</span></div><div><strong>{state.loading||state.error?'—':state.records.filter(row=>row.needs_attention).length}</strong><span>Need recovery</span></div><div><strong>{state.loading||state.error?'—':state.records.filter(row=>row.receipt_retained).length}</strong><span>Publication receipts retained</span></div></div>
  <div className="change-control__toolbar"><label>Workspace<select value={source} onChange={event=>{setSource(event.target.value);setOffset(0);}}>{SOURCES.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label><label>Find in loaded records<input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Name, identifier or state"/></label></div>
  {state.loading&&<p role="status">Loading retained change evidence…</p>}
  {state.error&&<p role="alert">{state.error}</p>}
  {state.partial&&<p role="alert">Partial evidence: {state.coverage.filter(row=>row.status!=='available').map(row=>row.source).join(', ')} could not be read. Missing evidence does not mean no approvals exist.</p>}
  {!state.loading&&!state.error&&<><p className="change-control__scope">History page {Math.floor(offset/25)+1}: up to 25 records per source. Counts are records loaded, not unique changes or all history. Publication receipts describe retained execution; currentness must be rechecked before a new write.</p><div className="change-control__table"><table><thead><tr><th scope="col">Change evidence</th><th scope="col">Review / authorization</th><th scope="col">Execution</th><th scope="col">Delivery</th><th scope="col">Inspect</th></tr></thead><tbody>{rows.map(row=><tr key={row.record_key}><td><strong>{row.title}</strong><small>{row.category} · {row.updated_at||'Time unavailable'}</small></td><td>{row.review_state}</td><td><span className={row.needs_attention?'change-control__attention':''}>{row.execution_state}</span></td><td>{row.delivery_state}</td><td><button onClick={()=>setSelected(row)} aria-label={`Inspect ${row.title}`}>Inspect</button></td></tr>)}{!rows.length&&<tr><td colSpan={5}>{state.records.length?'No loaded records match the filter.':'No retained change evidence was returned by the selected sources.'}</td></tr>}</tbody></table></div><nav className="change-control__toolbar" aria-label="Change history pages"><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous history</button><button disabled={!state.has_more} onClick={()=>setOffset(offset+25)}>Next history</button></nav></>}
  {selected&&<section className="change-control__detail" aria-label="Selected change evidence"><header><h3>{selected.title}</h3><button onClick={()=>setSelected(null)}>Close details</button></header><p>{selected.category} · {selected.identifier}</p><dl><dt>Owning service</dt><dd>{selected.owner_service}</dd><dt>Authorization scope</dt><dd>{selected.authorization_kind} · {selected.authorization_actor||'No actor recorded'}</dd><dt>Policy checks</dt><dd>{selected.policy_assessment} (not approval)</dd><dt>Review</dt><dd>{selected.review_state}</dd><dt>Execution</dt><dd>{selected.execution_state}</dd><dt>Delivery</dt><dd>{selected.delivery_state}</dd></dl><p>{selected.currentness}</p><details><summary>Retained identifiers and digests</summary><dl>{Object.entries(selected.evidence||{}).map(([key,value])=><React.Fragment key={key}><dt>{key}</dt><dd>{value}</dd></React.Fragment>)}</dl></details><a href={selected.workspace?.startsWith('#/')?selected.workspace:'#/change-control'}>Open owning workflow</a><p>Historical records are not automatically converted into approved change orders.</p></section>}
 </section>;
}
