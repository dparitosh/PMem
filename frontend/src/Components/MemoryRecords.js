import React, {useEffect, useState} from 'react';
import {agenticClient} from '../services/agenticApi';
import {buildSemanticServiceUrl} from '../config';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import {formatChatMarkdown} from '../utils/chatMarkdown';
import './MemoryRecords.css';

export default function MemoryRecords() {
  const [report,setReport]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0),[query,setQuery]=useState('');
  useEffect(()=>{
    const controller=new AbortController(); let active=true;
    setReport(null);setError('');
    const reset=()=>{active=false;controller.abort();setReport(null);setError('Access changed. Refresh memory records after reconnecting.');};
    const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-expired','depo:session-replaced'];
    events.forEach(name=>window.addEventListener(name,reset));
    agenticClient.get(buildSemanticServiceUrl('agentic','/api/v1/memory/records'),{signal:controller.signal,timeout:15000})
      .then(({data})=>{if(active)setReport(data);}).catch(e=>{if(active)setError(apiErrorMessage(e));});
    return()=>{active=false;controller.abort();events.forEach(name=>window.removeEventListener(name,reset));};
  },[revision]);
  const records=(report?.records||[]).filter(r=>`${r.user_request} ${r.resolved_query} ${r.graph_context?.ontology||''}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="memory-records" aria-label="Memory records">
    <header><div><h2>Knowledge and conversation memory</h2><p>Review your saved questions, answers and selected engineering context.</p></div><button onClick={()=>setRevision(v=>v+1)}>Refresh memory records</button></header>
    <div className="memory-records__types"><div><strong>Conversation memory</strong><p>Saved questions and answers for the connected user.</p></div><div><strong>Contextual memory</strong><p>The selected ontology and business record retained with each answer.</p></div><div><strong>Long-term knowledge</strong><p>Published engineering records in <a href="#/graph">Graph Explorer</a>. Saved answers do not replace current source evidence.</p></div></div>
    {error?<p role="alert">{error}</p>:!report?<p role="status">Loading your retained records…</p>:<>
      <label>Find a saved question<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search questions or ontology"/></label>
      <p>{records.length} of the latest {report.limit} retained records shown. {report.notice}</p>
      {!records.length&&<p>No matching retained conversations for this connected user.</p>}
      {records.map(record=><article key={record.job_id}><h3>{record.user_request}</h3><p><time>{record.finished_at?new Date(record.finished_at).toLocaleString():'Time not recorded'}</time> · {record.answerable===false?'Evidence was insufficient':'Saved answer'}</p>
        <p><strong>Resolved question:</strong> {record.resolved_query||record.user_request}</p>
        <p><strong>Ontology context:</strong> {record.graph_context?.ontology||'No ontology selected'}</p>
        <details><summary>Read retained answer and context</summary><div className="memory-records__answer" dangerouslySetInnerHTML={{__html:formatChatMarkdown(record.response,record.evidence||[])}}/><p>This is the retained answer, not a new analysis.</p><details><summary>Retained business identity</summary>{record.graph_context?.node_id||'No selected business record'}</details></details>
      </article>)}
      <details><summary>Where this memory is stored</summary><p>{report.storage?.conversation}</p><p>{report.storage?.context}</p><p>{report.storage?.knowledge}</p><p>Recall is bounded to the authorized owner and business scope. Retention does not train the model or approve a reusable lesson.</p></details>
    </>}
  </section>;
}
