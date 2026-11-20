import React, {useEffect,useRef,useState} from 'react';
import useRouteView from '../app/useRouteView';
import {graphApi} from '../services/graphApi';
import {dataPipelineAPI} from '../services/apiClient';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import './GraphAnalyticsPage.css';
import {businessDisplayName} from '../features/recommendations/businessDisplayName';

const METHODS={
 'pagerank':['Structural importance','Which records are most connected through the selected relationships?'],
 'personalized-pagerank':['Relevance to a selected record','Which records are structurally relevant to this part?'],
 'node-similarity':['Comparable neighborhoods','Which records share the same relationship context?'],
 'traceability':['Recorded traceability paths','Which recorded two-step paths connect the selected record?'],
 'triangle-count':['Connected clusters','Where do three records form a closed relationship cluster?'],
};
const ALGORITHMS=Object.keys(METHODS);
const local=value=>String(value).split(/[#/:]/).pop() || String(value);
const recordName=node=>{
 const name=node?.name;
 const fallback=node?.role?`${node.role} (name not recorded)`:'Business name not recorded';
 return typeof name==='string'&&(/^(?:id\d+|_\d+_\d+_\d+_[A-Za-z0-9_]{15,})$/.test(name))?fallback:businessDisplayName(name,fallback);
};
const pathText=row=>row.nodes.map((node,index)=>{
 if(!index)return recordName(node);
 const previous=row.nodes[index-1];
 const edge=row.edges.find(item=>(item.source===previous.node_id&&item.target===node.node_id)||(item.target===previous.node_id&&item.source===node.node_id));
 return `${edge?.source===previous.node_id?' → ':edge?.target===previous.node_id?' ← ':' — '}${recordName(node)}`;
}).join('');
const readSource=()=>new URLSearchParams(window.location.hash.split('?')[1] || '').get('ontology_id') || '';
export default function GraphAnalyticsPage({embedded=false}){
 const [algorithm,setAlgorithm]=useRouteView(ALGORITHMS,'pagerank',undefined,embedded?'#/reports':'#/graph-analytics',embedded?'algorithm':'view');
 const [source,setSource]=useState(readSource),[sources,setSources]=useState([]),[options,setOptions]=useState(null);
 const [seed,setSeed]=useState(''),[predicates,setPredicates]=useState([]),[result,setResult]=useState(null);
 const [error,setError]=useState(''),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const [sourceNames,setSourceNames]=useState({});
 const pending=useRef(null);
 const needsSeed=!['pagerank','triangle-count'].includes(algorithm);
 useEffect(()=>{
  const route=()=>setSource(readSource());
  const credentials=()=>{pending.current?.abort();setSources([]);setSourceNames({});setOptions(null);setResult(null);setRevision(value=>value+1);};
  window.addEventListener('hashchange',route);window.addEventListener('depo:credentials-changed',credentials);window.addEventListener('depo:access-rejected',credentials);
  return()=>{pending.current?.abort();window.removeEventListener('hashchange',route);window.removeEventListener('depo:credentials-changed',credentials);window.removeEventListener('depo:access-rejected',credentials);};
 },[]);
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);setError('');
  dataPipelineAPI.runs(100,{signal:controller.signal,timeout:15000}).then(response=>{if(!controller.signal.aborted)setSourceNames(Object.fromEntries((response.data?.runs || []).filter(row=>typeof row.run_id==='string'&&typeof row.source_name==='string').map(row=>[row.run_id,row.source_name])));}).catch(()=>{});
  graphApi.computationOptions('',controller.signal).then(response=>{if(!controller.signal.aborted){if(!Array.isArray(response.data?.sources))throw new Error('Published source list is invalid');setSources(response.data.sources);}}).catch(failure=>{if(!controller.signal.aborted)setError(apiErrorMessage(failure));}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[revision]);
 useEffect(()=>{
  const controller=new AbortController();setOptions(null);setSeed('');setPredicates([]);setResult(null);setError('');
  if(!source)return()=>controller.abort();
  setLoading(true);
  graphApi.computationOptions(source,controller.signal).then(response=>{
   if(controller.signal.aborted)return;
   const value=response.data;
   if(!Array.isArray(value?.nodes)||!Array.isArray(value?.predicates)||value.sources?.length!==1||value.sources[0].ontology_id!==source)throw new Error('Published selection is invalid');
   setOptions(value);setPredicates(value.predicates.slice(0,12));
  }).catch(failure=>{if(!controller.signal.aborted)setError(apiErrorMessage(failure));}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[source,revision]);
 useEffect(()=>{pending.current?.abort();setBusy(false);setResult(null);},[source,algorithm,seed,predicates,revision]);
 const selectSource=value=>{
  const params=new URLSearchParams(window.location.hash.split('?')[1] || '');
  if(value)params.set('ontology_id',value);else params.delete('ontology_id');
  window.history.pushState(null,'',`${embedded?'#/reports':'#/graph-analytics'}?${params}`);window.dispatchEvent(new HashChangeEvent('hashchange'));
 };
 const execute=async(retained=false)=>{
  pending.current?.abort();const controller=new AbortController();pending.current=controller;setBusy(true);setError('');
  const intent={ontology_id:source,publication_id:options.sources[0].publication_id,algorithm,predicates,node_id:needsSeed?seed:'',top_n:10};
  try{
   const response=retained?await graphApi.computationEvidence(result.evidence_id,source,controller.signal):await graphApi.computeGraph(intent,controller.signal);
   if(controller.signal.aborted)return;
   const value=response.data;
   if(value?.ontology_id!==source||value.publication_id!==intent.publication_id||value.algorithm!==algorithm||value.advisory_only!==true||value.approval_granted!==false||!Array.isArray(value.results)||!Number.isInteger(value.result_count)||value.result_count!==value.results.length||!value.evidence_id)throw new Error('Graph analysis returned mismatched evidence');
   setResult(value);
  }catch(failure){if(!controller.signal.aborted){setResult(null);setError(apiErrorMessage(failure));}}
  finally{if(!controller.signal.aborted)setBusy(false);}
 };
 const ready=options&&predicates.length>0&&(!needsSeed||seed)&&!loading&&!busy;
 return <section className="graph-analytics" aria-label="Graph Analytics">
  <header><h2>Graph Analytics</h2><p>Explore recorded engineering relationships for a published source version.</p></header>
  <form onSubmit={event=>{event.preventDefault();if(ready)execute();}}>
   <div className="graph-analytics-fields">
    <label>Published source<select value={source} onChange={event=>selectSource(event.target.value)} disabled={loading}><option value="">Choose a published source</option>{sources.map(row=><option key={row.ontology_id} value={row.ontology_id}>{sourceNames[row.publication_id] || row.name}{row.published_at?` · ${new Date(row.published_at).toLocaleString()}`:''}</option>)}</select></label>
    <label>Business question<select value={algorithm} onChange={event=>setAlgorithm(event.target.value)}>{ALGORITHMS.map(id=><option key={id} value={id}>{METHODS[id][0]}</option>)}</select></label>
    {needsSeed&&<label>Reference record<select value={seed} onChange={event=>setSeed(event.target.value)}><option value="">Choose a business record</option>{options?.nodes.map((row,index)=><option key={row.node_id} value={row.node_id}>{recordName({...row,name:row.name||`Unnamed record ${index+1}`})}{row.record_types?.length?` · ${row.record_types.filter(value=>!value.endsWith('NamedIndividual')).map(local).join(', ')}`:''}{row.revision?` · Rev ${row.revision}`:''}</option>)}</select></label>}
   </div>
   <p>{METHODS[algorithm][1]}</p>
   {options&&<fieldset><legend>Relationships ({predicates.length} selected, up to 12)</legend><div className="graph-analytics-predicates">{options.predicates.map(value=><label key={value} title={value}><input type="checkbox" checked={predicates.includes(value)} disabled={!predicates.includes(value)&&predicates.length>=12} onChange={event=>setPredicates(current=>event.target.checked?[...current,value]:current.filter(item=>item!==value))}/>{local(value)}</label>)}</div>{!options.predicates.length&&<p>No eligible relationships in this published source.</p>}{options.predicates_limited&&<p role="status">Only the first 100 relationship types are listed.</p>}</fieldset>}
   <div className="graph-analytics-actions"><button type="submit" disabled={!ready}>{busy?'Analysing…':'Analyse graph'}</button><button type="button" onClick={()=>setRevision(value=>value+1)} disabled={busy}>Refresh sources</button><a href="#/admin?view=agents">Agent Control</a></div>
  </form>
  {loading&&<p role="status">Loading published selections…</p>}{error&&<p role="alert">{error}</p>}
  {!loading&&!sources.length&&!error&&<p role="status">No current published sources are available.</p>}
  {result&&<section aria-label="Graph analysis result">
   <h3>{METHODS[algorithm][0]}</h3><p>{result.interpretation}</p>
   <dl className="graph-analytics-totals"><div><dt>Records assessed</dt><dd>{result.coverage.nodes}</dd></div><div><dt>Relationships assessed</dt><dd>{result.coverage.edges}</dd></div><div><dt>Results shown</dt><dd>{result.result_count}</dd></div>{result.global_triangle_count!=null&&<div><dt>Closed clusters</dt><dd>{result.global_triangle_count}</dd></div>}</dl>
   <p>Evidence for review · Approval not granted{result.results_limited?' · Top 10 results':''}</p>
   <table><thead><tr><th>{algorithm==='traceability'?'Investigation path':'Business record'}</th><th>{algorithm==='triangle-count'?'Triangle count':algorithm==='traceability'?'Relationship evidence':'Structural score'}</th></tr></thead><tbody>{result.results.map((row,index)=><tr key={row.node_id || index}><td>{row.nodes?pathText(row):<><strong>{recordName(row)}</strong>{row.record_types?.length>0&&<div>{row.record_types.map(local).join(', ')}</div>}<details><summary>Record reference</summary>{row.node_id}</details></>}</td><td>{row.edges?row.edges.map(edge=>`${recordName(row.nodes.find(node=>node.node_id===edge.source))} → ${recordName(row.nodes.find(node=>node.node_id===edge.target))}: ${local(edge.predicate)}`).join(' / '):row.triangle_count??Number(row.score).toFixed(4)}</td></tr>)}</tbody></table>
   {!result.results.length&&<p>No matching structures in the selected relationships.</p>}
   <details><summary>Source version and retained evidence</summary><dl><dt>Source</dt><dd>{source}</dd><dt>Publication</dt><dd>{result.publication_id}</dd><dt>Computed</dt><dd>{result.computed_at}</dd><dt>Evidence reference</dt><dd>{result.evidence_id}</dd><dt>Projection</dt><dd>{result.projection_digest}</dd></dl><p>{result.currentness}</p><button type="button" disabled={busy} onClick={()=>execute(true)}>Read retained evidence</button></details>
   <a href="#/recommendations">Review engineering constraints and impact</a>
  </section>}
 </section>;
}
