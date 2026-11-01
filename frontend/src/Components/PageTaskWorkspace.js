import React, { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState } from 'react';
import agenticAPI from '../services/agenticApi';
import { pageTaskProfiles } from '../services/pageTasks';
import { pageLabel } from '../app/navigation';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import TaskProgress from './TaskProgress';
import './PageTaskWorkspace.css';
import {workspaceContracts, taskIsPending} from '../workflows/workspaceContracts';
import {taskPollDelay} from '../workflows/taskPolling';
const AgentProposalPanel = lazy(() => import('./AgentProposalPanel'));
const ReadGoalPanel = lazy(() => import('./ReadGoalPanel'));

export default function PageTaskWorkspace({ page }) {
  const profile = pageTaskProfiles[page];
  const [open,setOpen] = useState(false), [rows,setRows] = useState([]), [error,setError] = useState('');
  const [offset,setOffset] = useState(0), [more,setMore] = useState(false), [revision,setRevision] = useState(0);
  const [selected,setSelected] = useState(null), [run,setRun] = useState(null), [notice,setNotice] = useState('');
  const [busy,setBusy] = useState(false), [ontology,setOntology] = useState('');
  const [investigationOpen,setInvestigationOpen] = useState(false);
  const generation = useRef(0), controlLock = useRef(false);
  const [loading,setLoading] = useState(false);
  const listRequest = useRef(null), detailRequest = useRef(null);
  useEffect(()=>{
    generation.current++;controlLock.current=false;setBusy(false);
    setSelected(null);setRun(null);setRows([]);setNotice('');setOntology('');setOffset(0);setInvestigationOpen(false);
    return ()=>{generation.current++;listRequest.current?.abort();detailRequest.current?.abort();};
  },[page]);
  useEffect(() => {
    if (!open || !profile) return;
    let stopped = false, timer, failures = 0, accessRejected = false;
    async function load() {
      if (document.hidden) { timer=setTimeout(load,15000); return; }
      listRequest.current?.abort(); const controller = new AbortController(); listRequest.current=controller;
      setLoading(true);
      let delay = 15000;
      try {
        const response = await agenticAPI.pageTasks(page,offset,{signal:controller.signal,timeout:15000});
        if (controller.signal.aborted || stopped) return;
        const data=response.data;
        if (data?.page !== page || !Array.isArray(data.tasks) || data.tasks.some(row=>!row.run_id || !['goal','workflow','tool'].includes(row.kind) || row.page_context?.page !== page)) throw new Error('Task history returned an incompatible page scope.');
        setRows(data.tasks); setMore(data.has_more===true); setError('');
        failures=0;accessRejected=false;
      } catch (failure) { if (!controller.signal.aborted && !stopped) {
        delay=taskPollDelay(failure,++failures);
        if(delay===null){accessRejected=true;setRows([]);setSelected(null);setRun(null);setMore(false);}
        setError(apiErrorMessage(failure,'Task history is unavailable. Existing tasks are retained.'));
      } }
      finally {if(!controller.signal.aborted&&!stopped)setLoading(false);}
      if (!stopped && !controller.signal.aborted && delay!==null) timer=setTimeout(load,delay);
    }
    load();
    const update=()=>{clearTimeout(timer);if(!accessRejected)load();};
    const verified=()=>{accessRejected=false;update();};
    const visibility=()=>{clearTimeout(timer);if(document.hidden)listRequest.current?.abort();else if(!accessRejected)load();};
    window.addEventListener('depo:page-task-updated',update);
    window.addEventListener('depo:access-verified',verified);
    document.addEventListener('visibilitychange',visibility);
    return ()=>{stopped=true;clearTimeout(timer);listRequest.current?.abort();window.removeEventListener('depo:page-task-updated',update);window.removeEventListener('depo:access-verified',verified);document.removeEventListener('visibilitychange',visibility);};
  },[open,page,offset,revision]);
  useEffect(()=>{
    const clear=()=>{generation.current++;controlLock.current=false;setBusy(false);setLoading(false);listRequest.current?.abort();detailRequest.current?.abort();setRows([]);setSelected(null);setRun(null);setError('');setNotice('');setOntology('');setInvestigationOpen(false);setOpen(false);setOffset(0);};
    const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-expired','depo:session-replaced'];
    events.forEach(event=>window.addEventListener(event,clear));
    return ()=>events.forEach(event=>window.removeEventListener(event,clear));
  },[]);
  useLayoutEffect(()=>{generation.current++;controlLock.current=false;setBusy(false);return()=>{generation.current++;};},[page,selected,open]);
  useEffect(()=>{
    if (!open || !selected || selected.kind==='goal') return;
    let stopped=false,timer,failures=0,accessRejected=false;
    async function load(){
      if(document.hidden){timer=setTimeout(load,3000);return;}
      detailRequest.current?.abort();const controller=new AbortController();detailRequest.current=controller;
      try {
        const response=await agenticAPI.pageTask(selected.kind,selected.run_id,{signal:controller.signal,timeout:15000});
        if(stopped || controller.signal.aborted)return;
        if(response.data?.run_id!==selected.run_id)throw new Error('Task reference mismatch; no action was performed.');
        if(response.data.allowed_actions!=null && (!Array.isArray(response.data.allowed_actions)||response.data.allowed_actions.some(action=>!['pause','resume','cancel'].includes(action))))throw new Error('Invalid workflow controls; refresh server status.');
        setRun(response.data);
        failures=0;accessRejected=false;setNotice('');
        if(taskIsPending(response.data))timer=setTimeout(load,3000);
      }catch(failure){if(!stopped&&!controller.signal.aborted){setRun(null);setNotice(apiErrorMessage(failure,'Task details unavailable; do not repeat a write.'));const delay=taskPollDelay(failure,++failures,3000);if(delay!==null)timer=setTimeout(load,delay);else accessRejected=true;}}
    }
    const visibility=()=>{clearTimeout(timer);if(document.hidden)detailRequest.current?.abort();else if(!accessRejected)load();};
    document.addEventListener('visibilitychange',visibility);
    load();return()=>{stopped=true;clearTimeout(timer);detailRequest.current?.abort();document.removeEventListener('visibilitychange',visibility);};
  },[open,selected,revision]);
  if (!profile) return null;
  return <section className="page-task-workspace" aria-label={`${pageLabel(page)} tasks`}>
    <button type="button" className="page-task-toggle" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>Guided work &amp; tasks <span>{pageLabel(page)}</span></button>
    {open && <div className="page-task-body">
      <ol className="page-task-steps">{profile.steps.map(step=><li key={step}>{step}</li>)}</ol>
      {workspaceContracts[page] && <div className="page-task-contract" role="region" aria-label="Workflow responsibilities"><p><strong>Execution</strong> {workspaceContracts[page].execution}</p><p><strong>Agent role</strong> {workspaceContracts[page].agent}</p><p><strong>Verify outcome</strong> {workspaceContracts[page].receipt} <a href={`#/${workspaceContracts[page].next}`}>{workspaceContracts[page].nextLabel}</a></p></div>}
      <p>{profile.link===page ? profile.action : <a href={`#/${profile.link}`}>{profile.action}</a>}. Domain imports and processing jobs retain their existing histories; this list tracks page-tagged agent investigations and executions.</p>
      {!profile.native && <details open={investigationOpen} onToggle={event=>setInvestigationOpen(event.currentTarget.open)}><summary>Start a scoped investigation or reviewed action</summary>
        <label>Ontology/source ID for this task (optional)<input value={ontology} maxLength={256} onChange={event=>setOntology(event.target.value)} /></label>
        <p>{ontology ? `This task is bound to ${ontology}.` : 'No ontology selected for this task. Reads may cover the permitted shared context; select a source to narrow them.'}</p>
        {investigationOpen && <Suspense fallback={<p>Loading task controls…</p>}><AgentProposalPanel key={ontology} title={`${pageLabel(page)} investigation`} agentIds={profile.agents} context={{page,...(ontology?{ontology_id:ontology}:{})}} /></Suspense>}
      </details>}
      <h3>Retained page tasks</h3><p>Statuses are the latest retained records. Open a task to check its current server state. Older runs without a page tag remain in their domain history.</p>
      <button type="button" onClick={()=>setRevision(value=>value+1)}>Refresh task history</button>
      {error && <p role="alert">{error}</p>}
      {loading && <p role="status">Loading task history…</p>}
      {!loading && !error && !rows.length && <p>No retained agent tasks on this page.</p>}
      <ul>{rows.map(row=><li key={`${row.kind}:${row.run_id}`}><button type="button" onClick={()=>{setSelected(row);setRun(null);setNotice('');}}>{row.title}</button> · {String(row.status || 'unknown').replaceAll('_',' ')} {row.page_context.ontology_id && <small> · {row.page_context.ontology_id}</small>}</li>)}</ul>
      <button type="button" disabled={!offset} onClick={()=>{setSelected(null);setRun(null);setOffset(Math.max(0,offset-20));}}>Newer tasks</button>{' '}
      <button type="button" disabled={!more} onClick={()=>{setSelected(null);setRun(null);setOffset(offset+20);}}>Older tasks</button>
      {selected && <section aria-label="Selected retained task"><button type="button" onClick={()=>{detailRequest.current?.abort();setSelected(null);setRun(null);}}>Close task</button>
        {selected.kind==='goal' ? <Suspense fallback={<p>Loading retained investigation…</p>}><ReadGoalPanel key={selected.run_id} agent={selected.agent_id} task={selected.title} context={selected.page_context} initialRunId={selected.run_id} resumeOnly /></Suspense> : <>
          <TaskProgress run={run} kind={selected.kind} />
          {selected.kind==='workflow' && run?.allowed_actions?.map(action=><button key={action} disabled={busy} type="button" onClick={async()=>{
            if(controlLock.current)return;
            controlLock.current=true;const current=generation.current;
            setBusy(true);setNotice('');setRun(null);
            try{await agenticAPI.controlWorkflow(selected.run_id,action);if(current!==generation.current)return;setNotice(`${action} requested. The server applies controls at a safe task boundary; completed writes remain retained.`);setRevision(value=>value+1);}
            catch(failure){if(current===generation.current)setNotice(apiErrorMessage(failure,'Control was not confirmed. Refresh the task before retrying.'));}
            finally{if(current===generation.current){controlLock.current=false;setBusy(false);}}
          }}>{action[0].toUpperCase()+action.slice(1)} workflow</button>)}
          {run && !['completed','queued','running'].includes(run.status) && <p><a href="#/admin">Open Admin to inspect recovery and verified receipts</a>. No failed write is retried from this view.</p>}
        </>}
        {notice && <p role="status">{notice}</p>}
      </section>}
    </div>}
  </section>;
}
