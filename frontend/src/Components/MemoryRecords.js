import React, {useEffect, useState} from 'react';
import {agenticClient} from '../services/agenticApi';
import {buildSemanticServiceUrl} from '../config';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import {formatChatMarkdown} from '../utils/chatMarkdown';
import './MemoryRecords.css';

export default function MemoryRecords() {
  const readSelection=()=>{const params=new URLSearchParams(window.location.hash.split('?')[1]||'');return {job_id:params.get('job_id')||'',ontology_id:params.get('ontology_id')||''};};
  const [selection,setSelection]=useState(readSelection);
  useEffect(()=>{const changed=()=>setSelection(readSelection());window.addEventListener('hashchange',changed);window.addEventListener('popstate',changed);return()=>{window.removeEventListener('hashchange',changed);window.removeEventListener('popstate',changed);};},[]);
  const [report,setReport]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0),[query,setQuery]=useState('');
  useEffect(()=>{
    const controller=new AbortController(); let active=true;
    setReport(null);setError('');
    const reset=()=>{active=false;controller.abort();setReport(null);setError('Access changed. Refresh memory records after reconnecting.');};
    const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-expired','depo:session-replaced'];
    events.forEach(name=>window.addEventListener(name,reset));
    agenticClient.get(buildSemanticServiceUrl('agentic','/api/v1/memory/records'),{signal:controller.signal,timeout:15000,params:selection})
      .then(({data})=>{if(active)setReport(data);}).catch(e=>{if(active)setError(apiErrorMessage(e));});
    return()=>{active=false;controller.abort();events.forEach(name=>window.removeEventListener(name,reset));};
  },[revision,selection.job_id,selection.ontology_id]);
  const records=(report?.records||[]).filter(r=>`${r.user_request} ${r.resolved_query} ${r.graph_context?.ontology||''}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="memory-records" aria-label="Memory records">
    <header><div><h2>Knowledge and conversation memory</h2><p>Review your saved questions, answers and selected engineering context.</p></div><button onClick={()=>setRevision(v=>v+1)}>Refresh memory records</button></header>
    <div className="memory-records__types"><div><strong>Conversation memory</strong><p>Saved questions and answers for the connected user.</p></div><div><strong>Contextual memory</strong><p>The selected ontology and business record retained with each answer.</p></div><div><strong>Long-term knowledge</strong><p>Published engineering records in <a href="#/graph">Graph Explorer</a>. Saved answers do not replace current source evidence.</p></div></div>
    {error?<p role="alert">{error}</p>:!report?<p role="status">Loading your retained records…</p>:<>
      <label>Find a saved question<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search questions or ontology"/></label>
      <p>{selection.job_id?'Selected retained conversation.':`${records.length} of the latest ${report.limit} retained records shown${selection.ontology_id?' in this ontology scope':''}.`} {report.notice}</p>
      {!records.length&&<p>{selection.job_id?'The selected retained conversation is unavailable for the connected user and scope.':'No matches in this bounded set of retained conversations.'}</p>}
      {records.map(record=><article key={record.job_id}><h3>{record.user_request}</h3><p><time>{record.finished_at?new Date(record.finished_at).toLocaleString():'Time not recorded'}</time> · {record.answerable===false?'Evidence was insufficient':'Saved answer'}</p>
        <p><strong>Resolved question:</strong> {record.resolved_query||record.user_request}</p>
        <p><strong>Search scope:</strong> {record.graph_context?.ontology||'All available sources (no single ontology selected)'}</p>
        {record.retrieval?.grounding?.resolved_identity?.label&&<p><strong>Evidence record:</strong> {record.retrieval.grounding.resolved_identity.label}</p>}
        <details open={selection.job_id===record.job_id||undefined}><summary>Read retained answer and context</summary><div className="memory-records__answer" dangerouslySetInnerHTML={{__html:formatChatMarkdown(record.response,record.evidence||[])}}/><p>This is the retained answer, not a new analysis.</p><details><summary>Retained business identity</summary>{record.graph_context?.node_id||record.retrieval?.grounding?.resolved_identity?.resource_id||'No unique business identity retained'}</details></details>
      </article>)}
      <details><summary>Where this memory is stored</summary><p>{report.storage?.conversation}</p><p>{report.storage?.context}</p><p>{report.storage?.knowledge}</p><p>Recall is bounded to the authorized owner and business scope. Retention does not train the model or approve a reusable lesson.</p></details>
    </>}
  </section>;
}
