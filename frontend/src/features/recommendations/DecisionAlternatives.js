import React, {useEffect, useRef, useState} from 'react';
import ReadGoalPanel from '../../Components/ReadGoalPanel';
import {API_METHODS} from '../../services/apiClient';
import {apiErrorMessage} from '../../utils/apiErrorMessage';

export default function DecisionAlternatives({ready}) {
  const [name,setName]=useState('');
  const [selection,setSelection]=useState(null);
  const [matches,setMatches]=useState(null);
  const [question,setQuestion]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [run,setRun]=useState(null);
  const request=useRef(null);
  const generation=useRef(0);
  useEffect(()=>()=>{request.current?.abort();generation.current+=1;},[]);
  const reset=()=>{request.current?.abort();generation.current+=1;setBusy(false);setSelection(null);setMatches(null);setRun(null);setError('');};
  useEffect(()=>{
    const clear=()=>{reset();setQuestion('');};
    const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-expired','depo:session-replaced','depo:access-rejected','depo:ontologies-changed'];
    events.forEach(event=>window.addEventListener(event,clear));
    return()=>events.forEach(event=>window.removeEventListener(event,clear));
  },[]);
  const find=async event=>{
    event.preventDefault(); if(!ready||!name.trim()||busy)return;
    request.current?.abort();const controller=new AbortController();request.current=controller;
    const current=++generation.current;setBusy(true);setError('');setMatches(null);setSelection(null);
    try{
      const params=new URLSearchParams(window.location.hash.split('?')[1]||'');
      const scope=params.get('ontology_id')?{ontology_id:params.get('ontology_id')}:{};
      const {data}=await API_METHODS.recommendations.resolve(name.trim(),scope,{signal:controller.signal,timeout:30000});
      if(!Array.isArray(data?.matches)||data.matches.length>20||typeof data.truncated!=='boolean'||data.matches.some(row=>!row||typeof row.node_id!=='string'||!row.node_id||typeof row.name!=='string'||!row.scope||typeof row.scope!=='object'||Array.isArray(row.scope)||Object.entries(row.scope).some(([key,value])=>!['ontology_id','ontology_prefix'].includes(key)||typeof value!=='string'||value.length>256)))throw new Error('Object search returned invalid evidence.');
      if(controller.signal.aborted||current!==generation.current)return;
      if(data.matches.length===1&&!data.truncated)setSelection(data.matches[0]);else setMatches(data);
    }catch(failure){if(!controller.signal.aborted&&current===generation.current)setError(apiErrorMessage(failure));}
    finally{if(!controller.signal.aborted&&current===generation.current)setBusy(false);}
  };
  const context={page:'recommendations',decision_analysis:'alternatives',...(selection?{node_id:selection.node_id,...selection.scope}:{})};
  const task=selection&&question.trim()?`For the selected business object ${JSON.stringify(selection.name)}, retrieve its recorded alternatives and their linked evaluation evidence using graph.business_context at depth 2. ${question.trim()} Compare recorded values against the stated criteria. Report the preferred feasible option, costs, and why other options fail. Cite the retained observation and source record identifiers. If evidence is missing, identify it instead of assuming values. This is an advisory recommendation; do not approve or implement a change.`:'';
  return <section aria-label="Decision alternatives">
    <form className="recommendation-query" onSubmit={find}>
      <label>Investigation or business object<input value={name} maxLength={500} placeholder="Find a recorded investigation or product" onChange={event=>{reset();setName(event.target.value);}}/></label>
      <button type="submit" disabled={!ready||busy||!name.trim()}>{busy?'Finding...':'Find business objects'}</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {matches&&<div className="recommendation-object-matches"><p>{matches.matches.length?'Select the intended record.':'No matching records.'}{matches.truncated?' Refine the name for more results.':''}</p>{matches.matches.map(row=><p key={row.node_id}><button type="button" onClick={()=>{setSelection(row);setMatches(null);setError('');}}>{row.name}</button> <span>{row.scope.ontology_id||row.scope.ontology_prefix}</span></p>)}</div>}
    {selection&&<p role="status">Selected: <strong>{selection.name}</strong> <button type="button" onClick={reset}>Change selection</button></p>}
    <label className="decision-question">Decision criteria and objective<textarea rows={3} maxLength={4000} value={question} onChange={event=>setQuestion(event.target.value)} placeholder="State the required performance, constraints and objective for comparing recorded alternatives."/></label>
    <ReadGoalPanel agent="graph-analyst" task={task} context={context} compact startLabel="Recommend with agent" disabled={!ready||!selection||!question.trim()} onRunChange={setRun}/>
    {run?.status==='completed'&&run.result?.comparison&&<section className="recommendation-object-matches" aria-label="Alternative success criteria"><h3>Success criteria</h3><table><thead><tr><th>Alternative</th>{run.result.comparison.criteria.map(c=><th key={c.property}>{c.property.replace(/([a-z])([A-Z])/g,'$1 $2')}<br/>{c.operator} {c.limit} {c.unit}</th>)}<th>Incremental cost</th><th>Outcome</th></tr></thead><tbody>{run.result.comparison.alternatives.map(row=><tr key={row.record_id}><td>{row.name}<details><summary>Evidence</summary>{row.external_id} - {row.evaluation_ids.join(', ')}</details></td>{row.checks.map(c=><td key={c.property}>{c.values.join(' / ')||'Not established'}<br/>{c.status==='met'?'Meets':c.status==='not_met'?'Does not meet':'Needs evidence'}</td>)}<td>{row.cost} {row.cost_unit}</td><td>{run.result.comparison.preferred_record_ids.includes(row.record_id)?'Recommended':row.feasible?'Feasible':'Does not meet criteria'}</td></tr>)}</tbody></table></section>}
    {selection&&<a href={'#/graph?'+new URLSearchParams({ontology_id:selection.scope.ontology_id||'',node_id:selection.node_id}).toString()}>View supporting graph</a>}
  </section>;
}
