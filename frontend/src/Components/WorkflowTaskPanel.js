import React, { useEffect, useRef, useState } from 'react';
import agenticAPI from '../services/agenticApi';
import { publicationRecoveryScope, getCredentialProfile } from '../services/serviceAuth';

export default function WorkflowTaskPanel({ workflowId, inputs, label, disabled, onResult, governed = false, stepInputs, onActivityChange }) {
  const key = JSON.stringify(['depo:task-run', publicationRecoveryScope(), workflowId, inputs, stepInputs || null, governed]);
  const [run, setRun] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [runId, setRunId] = useState('');
  const [revision, setRevision] = useState(0);
  const [submissionUnknown, setSubmissionUnknown] = useState(false);
  const [recoveryId, setRecoveryId] = useState('');
  const resultHandler = useRef(onResult); resultHandler.current = onResult;
  const request = useRef(null);
  useEffect(() => {
    request.current?.abort(); setRun(null); setBusy(false); setError(''); setSubmissionUnknown(false);
    try {
      const retained = sessionStorage.getItem(key) || '';
      setRunId(retained === 'submission-unconfirmed' ? '' : retained);
      if (retained === 'submission-unconfirmed') {
        setSubmissionUnknown(true); setError('Task submission was not confirmed. Check workflow history before retrying.');
      }
    } catch { setRunId(''); }
    const clear = () => { request.current?.abort(); setRun(null); setBusy(false); setRecoveryId(''); setRevision(value => value + 1); };
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, clear));
    return () => { request.current?.abort(); events.forEach(event => window.removeEventListener(event, clear)); };
  }, [key]);
  useEffect(() => {
    const terminal = ['completed','cancelled','failed','timed_out'].includes(run?.status) && !run?.reconciliation_required;
    onActivityChange?.(busy || submissionUnknown || (!!runId && !terminal));
  }, [busy, submissionUnknown, runId, run?.status, run?.reconciliation_required, onActivityChange]);
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController(); let timer;
    const refresh = async () => {
      if (document.hidden) { timer = setTimeout(refresh, 3000); return; }
      try {
        const { data } = await agenticAPI.getRun(runId, 'workflow', { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (!data || data.run_id !== runId || data.workflow_id !== workflowId || !['running', 'queued', 'paused', 'completed', 'cancelled', 'failed', 'timed_out', 'interrupted', 'recoverable'].includes(data.status) ||
            (data.traces !== undefined && (!Array.isArray(data.traces) || data.traces.some(trace => !trace || typeof trace !== 'object' || Array.isArray(trace)))) ||
            (data.allowed_actions !== undefined && (!Array.isArray(data.allowed_actions) || data.allowed_actions.some(action => !['pause', 'resume', 'cancel'].includes(action))))) throw new Error('Invalid workflow status.');
        setRun(data); setError('');
        if (data.status === 'completed') resultHandler.current?.(data);
        else if (['running', 'queued'].includes(data.status)) timer = setTimeout(refresh, 3000);
      } catch (failure) { if (!controller.signal.aborted) { setError('Could not refresh this run. Status checks will retry; use Refresh status to check now.'); if (![401, 403, 404].includes(failure.response?.status)) timer = setTimeout(refresh, 10000); } }
    };
    refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [runId, workflowId, revision, key]);
  const start = async () => {
    if (busy) return;
    const controller = new AbortController(); request.current = controller; setBusy(true); setError('');
    try {
      const token = getCredentialProfile('GRAPH_READ_TOKEN');
      const approval = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
      if (!token || (governed && !approval)) throw new Error('Connect reader and governed agent access in Admin.');
      const execution = { ...(governed ? {approved_by:'ontology-merge-automation',approval_token:approval} : {}), ...(stepInputs ? {step_inputs:stepInputs} : {}) };
      try { sessionStorage.setItem(key, 'submission-unconfirmed'); } catch { /* server retains the workflow */ }
      const { data } = await agenticAPI.runWorkflow(workflowId, inputs, execution, { signal: controller.signal, ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}) });
      if (controller.signal.aborted) return;
      if (!data.run_id) throw new Error('Missing workflow identity.');
      setRunId(data.run_id);
      try { sessionStorage.setItem(key, data.run_id); } catch { setError('Run started; bookmark its ID because browser recovery storage is unavailable.'); }
    } catch (failure) { if (!controller.signal.aborted) { setSubmissionUnknown(true); setError('Task submission was not confirmed. Check workflow history before retrying.'); } }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  return <section className="depo-workflow-reconciliation" aria-label="Background agent task">
    <div><button type="button" className="depo-button" disabled={disabled || busy || !!runId || submissionUnknown || !getCredentialProfile('GRAPH_READ_TOKEN') || (governed && !getCredentialProfile('AGENTIC_APPROVAL_TOKEN'))} onClick={start}>{busy ? 'Submitting…' : label}</button>
    {runId && <button type="button" className="depo-button depo-button--secondary" onClick={() => setRevision(value => value + 1)}>Refresh status</button>}</div>
    {error && <p role="alert">{error}</p>}
    {submissionUnknown && !runId && <div>
      <label>Recover workflow ID <input value={recoveryId} onChange={event => setRecoveryId(event.target.value)} /></label>
      <button type="button" disabled={!recoveryId.trim()} onClick={() => {
        const id = recoveryId.trim(); setRunId(id); setSubmissionUnknown(false);
        try { sessionStorage.setItem(key, id); } catch { /* optional recovery */ }
      }}>Inspect retained workflow</button>
      <small>Find this task in agent workflow history. Inspect its status before submitting another merge.</small>
    </div>}
    {runId && <p role="status">Workflow {runId}: {run?.execution_state || run?.status || 'checking'}. Results remain retained after leaving this page.</p>}
    {run?.pending_step?.child_run_id && <p>Waiting for dependent data job: {String(run.pending_step.child_run_id)}. Workflow completion requires its result.</p>}
    {run?.allowed_actions?.map(action => <button type="button" key={action} disabled={busy} onClick={async () => {
      const controller = new AbortController(); request.current = controller; setBusy(true);
      try { await agenticAPI.controlWorkflow(runId, action, { signal: controller.signal }); if (!controller.signal.aborted) setRevision(value => value + 1); }
      catch { if (!controller.signal.aborted) setError('Control was not confirmed. Refresh status before retrying.'); }
      finally { if (!controller.signal.aborted) setBusy(false); }
    }}>{action}</button>)}
    {runId && <small>Controls take effect between tools. Completed writes remain retained.</small>}
    {runId && error && <p>Reconnect access and refresh this retained workflow. An inaccessible run cannot be cleared while its outcome is unverified.</p>}
    {['completed', 'cancelled', 'failed', 'timed_out'].includes(run?.status) && !run?.reconciliation_required && <button type="button" onClick={() => {
      try { sessionStorage.removeItem(key); } catch {} setRunId(''); setRun(null); setError('');
    }}>Prepare a new task</button>}
    {run?.traces?.length > 0 && <details><summary>Retained task report · {run.traces.length} steps</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 360, overflow: 'auto' }}>{JSON.stringify(run.traces, null, 2)}</pre></details>}
  </section>;
}
