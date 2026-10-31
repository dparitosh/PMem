import React, {useEffect, useRef, useState} from 'react';
import {dataPipelineAPI} from '../services/apiClient';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import './AvailableAnalytics.css';

const EVENTS=['depo:session-replaced','depo:session-expired','depo:credentials-cleared','depo:credentials-changed'];
export default function AvailableAnalytics({drafts=[], onPrepare}) {
  const [offset,setOffset]=useState(0),[revision,setRevision]=useState(0);
  const [state,setState]=useState({loading:true}),[detail,setDetail]=useState(null),[preview,setPreview]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const selected=useRef(null),generation=useRef(0),request=useRef(null);
  useEffect(()=>{
    const reset=()=>{generation.current++;request.current?.abort();selected.current=null;setDetail(null);setPreview(null);setError('');setBusy(false);setRevision(v=>v+1);};
    EVENTS.forEach(e=>window.addEventListener(e,reset));
    return()=>{EVENTS.forEach(e=>window.removeEventListener(e,reset));generation.current++;request.current?.abort();};
  },[]);
  useEffect(()=>{
    const controller=new AbortController();setState({loading:true});
    Promise.resolve().then(()=>dataPipelineAPI.analytics({limit:20,offset},{signal:controller.signal,timeout:15000})).then(response=>{
      if(!Array.isArray(response.data?.datasets)||!Number.isInteger(response.data?.total))throw new Error('Invalid analytics inventory response');
      if(!controller.signal.aborted){
        if(offset>0&&response.data.total<=offset){setOffset(0);return;}
        setState(response.data);
      }
    }).catch(failure=>{if(!controller.signal.aborted)setState({error:apiErrorMessage(failure,'Available analytics could not be loaded. This does not mean no analytics exists.')});});
    return()=>controller.abort();
  },[offset,revision]);
  async function inspect(runId, relation) {
    request.current?.abort();const controller=new AbortController();request.current=controller;
    const current=++generation.current;selected.current=runId;setBusy(true);setError('');setPreview(null);
    if(!relation)setDetail(null);
    try {
      const response=await (relation?dataPipelineAPI.analyticsData(runId,relation,{signal:controller.signal,timeout:15000}):dataPipelineAPI.analyticsDetail(runId,{signal:controller.signal,timeout:15000}));
      if(!controller.signal.aborted&&current===generation.current){
        if(relation){if(!Array.isArray(response.data?.rows)||!Array.isArray(response.data?.columns)||response.data.relation!==relation)throw new Error('Preview identity did not match');setPreview(response.data);}
        else {if(response.data?.run_id!==runId||!Array.isArray(response.data?.relations))throw new Error('Analytics detail did not match');setDetail(response.data);}
      }
    }catch(failure){if(!controller.signal.aborted&&current===generation.current)setError(apiErrorMessage(failure,'Analytics inspection failed. Retry the selected dataset.'));}
    finally{if(current===generation.current)setBusy(false);}
  }
  const rows=state.datasets||[];
  return <section className="available-analytics" aria-label="Available analytics">
    <header><div><h3>Analytics available for use</h3><p>Inspect data already loaded, design dimensions and KPIs, then review and publish a reusable product.</p></div><button type="button" onClick={()=>{request.current?.abort();generation.current++;setDetail(null);setPreview(null);setError('');setBusy(false);setRevision(v=>v+1);}}>Refresh analytics</button></header>
    <ol className="analytics-journey"><li>Choose a schema and source data</li><li>Define dimensions, measures and KPIs</li><li>Validate and load with a pipeline worker</li><li>Review ownership and semantic release</li><li>Publish and consume</li></ol>
    <div className="analytics-totals"><div><strong>{drafts.length}</strong> schema designs</div><div><strong>{state.loading||state.error?'—':state.total}</strong> loaded analytics datasets</div><div>Publication is a separate governed step</div></div>
    {state.loading&&<p role="status">Discovering receipt-backed analytics…</p>}
    {state.error&&<p role="alert">{state.error}</p>}
    {!state.loading&&!state.error&&state.total===0&&!rows.length&&<div className="analytics-empty"><h4>No materialized analytics datasets found</h4><p>The imported schemas are designs. Select one below to prepare validated data loading; retained files or a schema plan alone do not create consumable tables.</p></div>}
    {rows.length>0&&<><div className="analytics-table"><table><thead><tr><th>Dataset</th><th>Data available</th><th>Business definitions</th><th>Next step</th></tr></thead><tbody>{rows.map(row=><tr key={row.run_id}><td><strong>{row.schema}</strong><small>Loaded {row.loaded_at||'date not recorded'}</small></td><td>Operational data store · latest load: {row.latest_load_counts?.entities??'unknown'} entity records</td><td>{row.business_views?.filter(v=>v.kind==='dimension').length||0} dimensions · {row.business_views?.filter(v=>v.kind==='kpi').length||0} KPIs · {row.business_views?.filter(v=>['fact','aggregate'].includes(v.kind)).length||0} aggregate views</td><td><button type="button" disabled={busy} onClick={()=>inspect(row.run_id)}>Inspect dataset</button> <a href={`#/data-products?run_id=${encodeURIComponent(row.run_id)}`}>Review for publication</a></td></tr>)}</tbody></table></div>
      <p>{state.scope} Load counts describe the latest source load, not the total rows in a dataset.</p></>}
    <div className="analytics-pages"><button type="button" disabled={state.loading||offset===0} onClick={()=>setOffset(Math.max(0,offset-20))}>Previous datasets</button><span>Page {Math.floor(offset/20)+1}</span><button type="button" disabled={state.loading||state.next_offset==null} onClick={()=>setOffset(state.next_offset)}>Next datasets</button></div>
    <h4>Prepare analytics from an imported schema</h4>
    {drafts.length?<ul className="analytics-designs">{drafts.map(draft=><li key={draft.ontology_id}><strong>{draft.label||draft.name||'Imported schema'}</strong><span>Schema design · data loading and business definitions need review</span><button type="button" onClick={()=>onPrepare?.(draft.ontology_id)}>Prepare this schema</button></li>)}</ul>:<p><a href="#/import">Import a schema</a> to start a reviewable analytics design.</p>}
    {busy&&<p role="status">Reading analytics metadata…</p>}{error&&<p role="alert">{error}</p>}
    {detail&&<section aria-label="Analytics dataset details"><h4>{detail.schema}</h4><p>{detail.consumption}</p><p>Quality: {detail.quality_status}. Evidence: {detail.evidence_status}. Approval is not implied by a successful load.</p><a href={`#/data-flow?run_id=${encodeURIComponent(detail.run_id)}`}>Inspect source, validation and lineage</a> · <a href={`#/data-products?run_id=${encodeURIComponent(detail.run_id)}`}>Review and publish this dataset</a>
      {detail.relations_limited&&<p role="status">Showing the first 200 of {detail.relation_total} relations.</p>}
      <div className="analytics-table"><table><thead><tr><th>Table or view</th><th>Purpose / grain</th><th>Measures and keys</th><th>Consume</th></tr></thead><tbody>{detail.relations.map(item=><tr key={item.name}><td>{item.label}<small>{detail.schema}.{item.name}</small></td><td>{item.kind} · {item.grain}{item.description&&<p>{item.description}</p>}{item.unit&&<small>Unit: {item.unit}</small>}</td><td>{(item.output_columns||[]).map(c=><div key={c.name}>{c.name} · {c.aggregate||c.role}</div>)}<details><summary>Columns ({item.column_count})</summary><ul>{item.columns.map(c=><li key={c.name}>{c.name} · {c.type}</li>)}</ul></details></td><td>{item.available?<button type="button" disabled={busy} onClick={()=>inspect(detail.run_id,item.name)}>Preview data</button>:<span role="status">Physical relation missing; reconcile before use</span>}</td></tr>)}</tbody></table></div>
    </section>}
    {preview&&<section aria-label="Analytics data preview"><h4>Data preview: {preview.relation}</h4><p>Read-only sample · {preview.rows.length} rows · no guaranteed ordering. Text is limited to {preview.cell_character_limit} characters per cell.{preview.limited?' More data is available.':''}</p><div className="analytics-table"><table><thead><tr>{preview.columns.map(c=><th key={c.name}>{c.name}<small>{c.type}</small></th>)}</tr></thead><tbody>{preview.rows.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j}>{cell??'Not recorded'}</td>)}</tr>)}</tbody></table></div>{!preview.rows.length&&<p>No rows in this relation.</p>}</section>}
  </section>;
}
