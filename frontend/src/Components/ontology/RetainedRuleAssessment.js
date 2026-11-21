import React, {useEffect,useRef,useState} from 'react';
import {API_METHODS} from '../../services/apiClient';
import {apiErrorMessage} from '../../utils/apiErrorMessage';

const label=value=>(/^https?:|^urn:/.test(String(value||''))?String(value).split(/[#/]/).pop():String(value??'')).replace(/_/g,' ').replace(/([a-z])([A-Z])/g,'$1 $2');

export default function RetainedRuleAssessment({ontologyId}) {
  const [result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const pending=useRef(null);
  useEffect(()=>{
    const reset=()=>{pending.current?.abort();pending.current=null;setResult(null);setError('');setBusy(false);};
    reset();
    const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-expired','depo:session-replaced'];
    events.forEach(event=>window.addEventListener(event,reset));
    return()=>{pending.current?.abort();events.forEach(event=>window.removeEventListener(event,reset));};
  },[ontologyId]);
  const assess=async()=>{
    pending.current?.abort();const controller=new AbortController();pending.current=controller;
    setResult(null);setError('');setBusy(true);
    try {
      const {data}=await API_METHODS.ontology.assessRetainedRules(ontologyId,{signal:controller.signal,timeout:60000});
      if(controller.signal.aborted||pending.current!==controller)return;
      if(!data||data.ontology_id!==ontologyId||!['completed','no_rules','blocked'].includes(data.status)||!Array.isArray(data.rules)
        ||!data.summary||!['rules','executed','conclusions'].every(key=>Number.isInteger(data.summary[key])&&data.summary[key]>=0)
        ||data.rules.some(rule=>!rule||!Array.isArray(rule.rows)||typeof rule.truncated!=='boolean'||rule.rows.some(row=>!row||!Array.isArray(row.inputs)||row.inputs.some(input=>!input||typeof input.predicate!=='string'||typeof input.value!=='string'))))throw new Error('Rule assessment returned invalid or mismatched evidence.');
      setResult(data);
    } catch(failure) {if(!controller.signal.aborted&&pending.current===controller)setError(apiErrorMessage(failure,'Rule assessment could not be completed.'));}
    finally {if(!controller.signal.aborted&&pending.current===controller)setBusy(false);}
  };
  return <section aria-label="Retained inspection rules" style={{border:'1px solid var(--ui-border)',borderRadius:8,padding:12,marginBottom:12,fontSize:14}}>
    <h3>Inspection rules and findings</h3>
    <button type="button" disabled={!ontologyId||busy} onClick={assess}>{busy?'Assessing rules...':'Assess retained rules'}</button>
    {error&&<p role="alert">{error}</p>}
    {result?.status==='no_rules'&&<p role="status">No retained SWRL rules in this ontology release.</p>}
    {result?.status==='blocked'&&<p role="alert">SHACL prerequisites need attention. No rules were executed.</p>}
    {result?.status==='completed'&&<>
      <p role="status">{result.summary.executed} rules assessed ; {result.summary.conclusions} conclusions ; {result.shacl?.targeted_subjects} SHACL targets checked</p>
      <div style={{overflowX:'auto'}}><table><thead><tr><th>Rule</th><th>Record</th><th>Conclusion</th><th>Evidence</th></tr></thead><tbody>
        {result.rules.flatMap(rule=>rule.rows.length?rule.rows.map((row,index)=><tr key={rule.rule_id+index}>
          <td>{rule.name}</td><td>{row.subject_label}</td><td>{row.conclusion_label}</td><td><details><summary>Source evidence</summary>
            <ul>{row.inputs.map((input,i)=><li key={i}>{label(input.predicate)}: {label(input.value)}{input.asserted===false?' ; derived from declared hierarchy':''}</li>)}</ul>
          </details></td></tr>):[<tr key={rule.rule_id}><td>{rule.name}</td><td>-</td><td>No matching conclusions</td><td>{rule.source_facts} source facts checked</td></tr>])}
      </tbody></table></div>
      {result.rules.some(rule=>rule.truncated)&&<p role="status">Some conclusions exceed the display limit. Narrow the source before treating this as a complete report.</p>}
      <details><summary>Assessment details</summary><p>{result.assessment_id}</p><p>Source SHA-256: {result.artifact_sha256}</p><p>{result.scope}</p></details>
    </>}

  </section>;
}
