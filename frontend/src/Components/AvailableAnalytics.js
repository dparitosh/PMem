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
    <header><div><h3>Your data, ready for analysis</h3><p>Browse available records, or choose an imported source to prepare data for reporting.</p></div><button type="button" onClick={()=>{request.current?.abort();generation.current++;setDetail(null);setPreview(null);setError('');setBusy(false);setRevision(v=>v+1);}}>Refresh analytics</button></header>
    {state.loading&&<p role="status">Checking available data…</p>}
    {state.error&&<p role="alert">{state.error}</p>}
    {!state.loading&&!state.error&&state.total===0&&<div className="analytics-empty"><h4>Your reporting data is not ready yet</h4><p>You have imported the structure of your data. The next step is to add the business records you want to analyse.</p><p><strong>Choose a source below and select “Prepare data”.</strong> You can then add a data file, check it and choose the summaries you need.</p></div>}
    {rows.length>0&&<section aria-label="Data ready to explore"><h4>Ready to explore</h4><div className="analytics-table"><table><thead><tr><th>Data</th><th>What is available</th><th>What you can do</th></tr></thead><tbody>{rows.map(row=><tr key={row.run_id}><td><strong>{row.name||row.schema}</strong><small>Updated {row.loaded_at?new Date(row.loaded_at).toLocaleDateString():'date not recorded'}</small></td><td>{row.latest_load_counts?.entities??'Unknown'} records in the latest load<br/>{row.business_views?.length?row.business_views.map(view=>view.name).join(', '):'Individual records; reporting summaries have not been defined'}</td><td><button type="button" disabled={busy} onClick={()=>inspect(row.run_id)}>Browse data</button> <a href={`#/data-products?run_id=${encodeURIComponent(row.run_id)}`}>Review and share</a></td></tr>)}</tbody></table></div><p>Data is available to inspect. Sharing it as an approved product requires a separate review.</p></section>}
    {!state.loading&&!state.error&&(state.total>20||offset>0)&&<div className="analytics-pages"><button type="button" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-20))}>Previous datasets</button><span>Page {Math.floor(offset/20)+1}</span><button type="button" disabled={state.next_offset==null} onClick={()=>setOffset(state.next_offset)}>Next datasets</button></div>}
    <section aria-label="Sources to prepare"><h4>Choose data to prepare</h4><p>These sources describe how your data is organised. They are not yet reporting datasets.</p>
    {drafts.length?<div className="analytics-table"><table><thead><tr><th>Source</th><th>Current status</th><th>Next action</th></tr></thead><tbody>{drafts.map(draft=><tr key={draft.ontology_id}><td><strong>{draft.label||draft.name||'Imported source'}</strong></td><td><span className="analytics-status">Structure imported</span><small>Business data still needs to be selected and checked.</small></td><td><button type="button" className="analytics-primary" onClick={()=>onPrepare?.(draft.ontology_id)}>Prepare data<span className="analytics-sr-only"> for {draft.label||draft.name||'this source'}</span></button></td></tr>)}</tbody></table></div>:<p><a href="#/import">Add a data source</a> to get started.</p>}</section>
    <details className="analytics-help"><summary>How does data become a shared product?</summary><ol><li><strong>Add records.</strong> Choose a source and the data file that belongs to it.</li><li><strong>Check and summarise.</strong> Validate the records and select the groups and measures needed for your report.</li><li><strong>Review and share.</strong> An authorised reviewer approves ownership, meaning and quality before the product is published.</li></ol><p>Preparing data does not automatically approve or publish it.</p></details>
    {busy&&<p role="status">Opening your data…</p>}{error&&<p role="alert">{error}</p>}
    {detail&&<section aria-label="Analytics dataset details"><h4>Browse available records and reports</h4><p>Choose Preview data to see a sample. These records have been loaded; publishing them for reuse still requires review.</p><details><summary>Validation and technical details</summary><p>{detail.schema} · Quality: {detail.quality_status} · Evidence: {detail.evidence_status}</p><p>{detail.consumption}</p></details><a href={`#/data-flow?run_id=${encodeURIComponent(detail.run_id)}`}>Inspect source, validation and lineage</a> · <a href={`#/data-products?run_id=${encodeURIComponent(detail.run_id)}`}>Review and publish this dataset</a>
      {detail.relations_limited&&<p role="status">Showing the first 200 of {detail.relation_total} relations.</p>}
      <div className="analytics-table"><table><thead><tr><th>Records or report</th><th>What it contains</th><th>Available fields</th><th>Action</th></tr></thead><tbody>{detail.relations.map(item=><tr key={item.name}><td>{item.label}</td><td>{{'operational table':'Individual business records','relationship table':'Links between records',dimension:'Groups used to analyse records',kpi:'Defined business measure',fact:'Summary of records',aggregate:'Summary of records'}[item.kind]||item.kind}{item.description&&<p>{item.description}</p>}{item.unit&&<small>Unit: {item.unit}</small>}</td><td>{(item.output_columns||[]).map(c=><div key={c.name}>{c.name} · {c.aggregate||c.role}</div>)}<details><summary>Columns ({item.column_count})</summary><ul>{item.columns.map(c=><li key={c.name}>{c.name} · {c.type}</li>)}</ul></details></td><td>{item.available?<button type="button" disabled={busy} onClick={()=>inspect(detail.run_id,item.name)}>Preview data</button>:<span role="status">Physical relation missing; reconcile before use</span>}</td></tr>)}</tbody></table></div>
    </section>}
    {preview&&<section aria-label="Analytics data preview"><h4>Data preview: {preview.relation}</h4><p>Read-only sample · {preview.rows.length} rows · no guaranteed ordering. Text is limited to {preview.cell_character_limit} characters per cell.{preview.limited?' More data is available.':''}</p><div className="analytics-table"><table><thead><tr>{preview.columns.map(c=><th key={c.name}>{c.name}<small>{c.type}</small></th>)}</tr></thead><tbody>{preview.rows.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j}>{cell??'Not recorded'}</td>)}</tr>)}</tbody></table></div>{!preview.rows.length&&<p>No rows in this relation.</p>}</section>}
  </section>;
}
