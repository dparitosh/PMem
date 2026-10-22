import React, { lazy, Suspense, useEffect, useRef, useState } from 'react';
import agenticAPI from '../services/agenticApi';
import { pageTaskProfiles } from '../services/pageTasks';
import { pageLabel } from '../app/navigation';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import TaskProgress from './TaskProgress';
import ReadGoalPanel from './ReadGoalPanel';
import './PageTaskWorkspace.css';
const AgentProposalPanel = lazy(() => import('./AgentProposalPanel'));
const active = ['queued','running','dispatching','paused','interrupted'];

export default function PageTaskWorkspace({ page }) {
  const profile = pageTaskProfiles[page];
  const [open,setOpen] = useState(false), [rows,setRows] = useState([]), [error,setError] = useState('');
  const [offset,setOffset] = useState(0), [more,setMore] = useState(false), [revision,setRevision] = useState(0);
  const [selected,setSelected] = useState(null), [run,setRun] = useState(null), [notice,setNotice] = useState('');
  const [busy,setBusy] = useState(false), [ontology,setOntology] = useState('');
  const listRequest = useRef(null), detailRequest = useRef(null);
  useEffect(() => {
    if (!open || !profile) return;
    let stopped = false, timer;
    async function load() {
      if (document.hidden) { timer=setTimeout(load,15000); return; }
      listRequest.current?.abort(); const controller = new AbortController(); listRequest.current=controller;
      try {
        const response = await agenticAPI.pageTasks(page,offset,{signal:controller.signal,timeout:15000});
        if (controller.signal.aborted || stopped) return;
        const data=response.data;
        if (data?.page !== page || !Array.isArray(data.tasks) || data.tasks.some(row=>!row.run_id || !['goal','workflow','tool'].includes(row.kind) || row.page_context?.page !== page)) throw new Error('Task history returned an incompatible page scope.');
        setRows(data.tasks); setMore(data.has_more===true); setError('');
      } catch (failure) { if (!controller.signal.aborted && !stopped) setError(apiErrorMessage(failure,'Task history is unavailable. Existing tasks are retained.')); }
      if (!stopped) timer=setTimeout(load,15000);
    }
    load();
    const update=()=>{clearTimeout(timer);load();};
    window.addEventListener('depo:page-task-updated',update);
    return ()=>{stopped=true;clearTimeout(timer);listRequest.current?.abort();window.removeEventListener('depo:page-task-updated',update);};
  },[open,page,offset,revision]);
  useEffect(()=>{
    const clear=()=>{listRequest.current?.abort();detailRequest.current?.abort();setRows([]);setSelected(null);setRun(null);setError('');setNotice('');setOpen(false);setOffset(0);};
    const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-expired'];
    events.forEach(event=>window.addEventListener(event,clear));
    return ()=>events.forEach(event=>window.removeEventListener(event,clear));
  },[]);
  useEffect(()=>{
    if (!open || !selected || selected.kind==='goal') return;
    let stopped=false,timer;
    async function load(){
      if(document.hidden){timer=setTimeout(load,3000);return;}
      detailRequest.current?.abort();const controller=new AbortController();detailRequest.current=controller;
      try {
        const response=await agenticAPI.pageTask(selected.kind,selected.run_id,{signal:controller.signal,timeout:15000});
        if(stopped || controller.signal.aborted)return;
        if(response.data?.run_id!==selected.run_id)throw new Error('Task reference mismatch; no action was performed.');
        setRun(response.data);
        if(active.includes(response.data.status))timer=setTimeout(load,3000);
      }catch(failure){if(!stopped&&!controller.signal.aborted){setRun(null);setNotice(apiErrorMessage(failure,'Task details unavailable; do not repeat a write.'));}}
    }
    load();return()=>{stopped=true;clearTimeout(timer);detailRequest.current?.abort();};
  },[open,selected,revision]);
  if (!profile) return null;
  return <section className="page-task-workspace" aria-label={`${pageLabel(page)} tasks`}>
    <button type="button" className="page-task-toggle" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>Guided work &amp; tasks <span>{pageLabel(page)}</span></button>
    {open && <div className="page-task-body">
      <ol className="page-task-steps">{profile.steps.map(step=><li key={step}>{step}</li>)}</ol>
      <p>{profile.link===page ? profile.action : <a href={`#/${profile.link}`}>{profile.action}</a>}. Domain imports and processing jobs retain their existing histories; this list tracks page-tagged agent investigations and executions.</p>
      {!profile.native && <details><summary>Start a scoped investigation or reviewed action</summary>
        <label>Ontology/source ID for this task (optional)<input value={ontology} maxLength={256} onChange={event=>setOntology(event.target.value)} /></label>
        <p>{ontology ? `This task is bound to ${ontology}.` : 'No ontology selected for this task. Reads may cover the permitted shared context; select a source to narrow them.'}</p>
        <Suspense fallback={<p>Loading task controls…</p>}><AgentProposalPanel key={ontology} title={`${pageLabel(page)} investigation`} agentIds={profile.agents} context={{page,...(ontology?{ontology_id:ontology}:{})}} /></Suspense>
      </details>}
      <h3>Retained page tasks</h3><p>Statuses are the latest retained records. Open a task to check its current server state. Older runs without a page tag remain in their domain history.</p>
      <button type="button" onClick={()=>setRevision(value=>value+1)}>Refresh task history</button>
      {error && <p role="alert">{error}</p>}
      {!error && !rows.length && <p>No retained agent tasks on this page.</p>}
      <ul>{rows.map(row=><li key={`${row.kind}:${row.run_id}`}><button type="button" onClick={()=>{setSelected(row);setRun(null);setNotice('');}}>{row.title}</button> · {String(row.status || 'unknown').replaceAll('_',' ')} {row.page_context.ontology_id && <small> · {row.page_context.ontology_id}</small>}</li>)}</ul>
      <button type="button" disabled={!offset} onClick={()=>{setSelected(null);setRun(null);setOffset(Math.max(0,offset-20));}}>Newer tasks</button>{' '}
      <button type="button" disabled={!more} onClick={()=>{setSelected(null);setRun(null);setOffset(offset+20);}}>Older tasks</button>
      {selected && <section aria-label="Selected retained task"><button type="button" onClick={()=>{detailRequest.current?.abort();setSelected(null);setRun(null);}}>Close task</button>
        {selected.kind==='goal' ? <ReadGoalPanel key={selected.run_id} agent={selected.agent_id} task={selected.title} context={selected.page_context} initialRunId={selected.run_id} resumeOnly /> : <>
          <TaskProgress run={run} kind={selected.kind} />
          {selected.kind==='workflow' && run?.allowed_actions?.map(action=><button key={action} disabled={busy} type="button" onClick={async()=>{
            setBusy(true);setNotice('');setRun(null);
            try{await agenticAPI.controlWorkflow(selected.run_id,action);setNotice(`${action} requested. The server applies controls at a safe task boundary; completed writes remain retained.`);setRevision(value=>value+1);}
            catch(failure){setNotice(apiErrorMessage(failure,'Control was not confirmed. Refresh the task before retrying.'));}
            finally{setBusy(false);}
          }}>{action[0].toUpperCase()+action.slice(1)} workflow</button>)}
          {run && !['completed','queued','running'].includes(run.status) && <p><a href="#/admin">Open Admin to inspect recovery and verified receipts</a>. No failed write is retried from this view.</p>}
        </>}
        {notice && <p role="status">{notice}</p>}
      </section>}
    </div>}
  </section>;
}
