import React, { useEffect, useRef, useState } from 'react';
import { agenticClient } from '../services/agenticApi';
import { buildSemanticServiceUrl } from '../config';
import { apiErrorMessage } from '../utils/apiErrorMessage';

export default function ReadGoalPanel({ agent, task, context }) {
  const [run, setRun] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState(() => { try { return sessionStorage.getItem('depo:read-goal') || ''; } catch { return ''; } });
  const request = useRef(null);
  const url = path => buildSemanticServiceUrl('agentic', `/api/v1/${path}`);
  useEffect(() => {
    const reset = () => { request.current?.abort(); setRun(null); setRunId(''); setError(''); setBusy(false); try { sessionStorage.removeItem('depo:read-goal'); } catch { /* optional bookmark */ } };
    const events = ['depo:credentials-cleared', 'depo:credentials-changed', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, reset));
    return () => { request.current?.abort(); events.forEach(event => window.removeEventListener(event, reset)); };
  }, []);
  useEffect(() => {
    if (!runId || (run && !['queued', 'running', 'interrupted'].includes(run.status))) return;
    let stopped = false, timer;
    const poll = async () => {
      if (document.hidden) { timer = setTimeout(poll, 3000); return; }
      const controller = new AbortController(); request.current = controller;
      try {
        const response = await agenticClient.get(url(`goals/${encodeURIComponent(runId)}`), { signal: controller.signal });
        if (!stopped) {
          setRun(response.data); setError('');
          if (['queued', 'running', 'interrupted'].includes(response.data.status)) timer = setTimeout(poll, 3000);
        }
      } catch (failure) {
        if (!stopped && !controller.signal.aborted) { setError(apiErrorMessage(failure)); timer = setTimeout(poll, 10000); }
      }
    };
    poll();
    return () => { stopped = true; clearTimeout(timer); request.current?.abort(); };
  }, [runId, run?.status]);
  const active = runId && (!run || ['queued', 'running', 'interrupted'].includes(run.status));
  return <section aria-label="Read-only goal investigation" className="depo-panel">
    <h4>Investigate a goal with the agent</h4>
    <p>The agent uses the configured model to plan subtasks, uses registered read tools, and revises its approach after a failed read. The plan and observations are retained in PostgreSQL across restarts. This mode cannot publish or modify the knowledge graph.</p>
    <button disabled={busy || active || !agent || !task?.trim()} onClick={async () => {
      request.current?.abort(); const controller = new AbortController(); request.current = controller;
      setBusy(true); setError('');
      try {
        const response = await agenticClient.post(url(`agents/${encodeURIComponent(agent)}/goals`), { task: task.trim(), context: context || {} }, { signal: controller.signal });
        if (!controller.signal.aborted) { setRun(response.data); setRunId(response.data.run_id); try { sessionStorage.setItem('depo:read-goal', response.data.run_id); } catch { /* optional bookmark */ } }
      } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
      finally { if (!controller.signal.aborted) setBusy(false); }
    }}>{busy ? 'Starting investigation…' : 'Start read-only investigation'}</button>
    {active && <button disabled={busy} onClick={async () => {
      request.current?.abort(); const controller = new AbortController(); request.current = controller;
      setBusy(true); setError('');
      try {
        const response = await agenticClient.post(url(`goals/${encodeURIComponent(runId)}/cancel`), {}, { signal: controller.signal });
        if (!controller.signal.aborted) setRun(response.data);
      } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
      finally { if (!controller.signal.aborted) setBusy(false); }
    }}>Cancel investigation</button>}
    {error && <p role="alert">{error}</p>}
    {run && <div aria-live="polite">
      <p><strong>Goal:</strong> {run.goal}</p>
      <p>Status: {run.status}. Decisions: {run.decisions} of {run.max_decisions}. Memory: {run.memory_backend}. Model: {run.provider || 'configured'} / {run.model || 'configured'}. Deadline: {run.deadline_at}.</p>
      {run.plans?.map(plan => <div key={plan.revision}><strong>Plan revision {plan.revision}</strong><ol>{plan.subtasks.map((step, index) => <li key={index}>{step}</li>)}</ol></div>)}
      {run.observations?.length > 0 && <ol aria-label="Agent observations">{run.observations.map(item => <li key={item.id}>
        <strong>{item.tool_id || 'Plan check'} — {item.status}</strong> · {item.id}
        {item.error_code && <p>{item.message || item.error_message || item.error_code} {item.status === 'failed' ? 'Retained for the next planning decision.' : ''}</p>}
        {item.result && <details><summary>Read evidence</summary><pre style={{whiteSpace:'pre-wrap', overflowWrap:'anywhere'}}>{JSON.stringify(item.result, null, 2)}</pre></details>}
      </li>)}</ol>}
      {run.result && <><strong>Model-assisted conclusion</strong><p>{run.result.summary}</p><p>Evidence: {run.result.evidence_steps.join(', ')}. Review the cited observations.</p></>}
      {run.error_code && <p role="status">{run.error_code}. Retained evidence remains available; no write was performed.</p>}
    </div>}
  </section>;
}
