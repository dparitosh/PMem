import React, { useEffect, useRef, useState } from 'react';
import { agenticClient } from '../services/agenticApi';
import { buildSemanticServiceUrl } from '../config';
import TaskProgress from './TaskProgress';
import { pageTaskContext, taskBookmarkKey } from '../services/pageTasks';
import { apiErrorMessage } from '../utils/apiErrorMessage';

export default function ReadGoalPanel({ agent, task, context, storageKey, initialRunId = '', resumeOnly = false, compact = false, disabled = false, startLabel = 'Start read-only investigation', onRunChange }) {
  const selectedContext = { ...(context || {}), ...pageTaskContext(context || {}) };
  const bookmark = storageKey || taskBookmarkKey(agent, selectedContext, task);
  const pendingKey = bookmark + ':pending';
  const [pending, setPending] = useState('');
  const [run, setRun] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState(() => { try { return initialRunId || sessionStorage.getItem(bookmark) || ''; } catch { return ''; } });
  const request = useRef(null);
  const url = path => buildSemanticServiceUrl('agentic', `/api/v1/${path}`);
  useEffect(() => {
    request.current?.abort(); setRun(null); setError(''); setBusy(false);
    try { setRunId(initialRunId || sessionStorage.getItem(bookmark) || ''); setPending(sessionStorage.getItem(pendingKey) || ''); }
    catch { setRunId(initialRunId); setPending(''); }
  }, [bookmark, initialRunId]);
  useEffect(() => {
    const reset = () => { request.current?.abort(); setRun(null); setRunId(''); setError(''); setBusy(false); try { sessionStorage.removeItem(bookmark); sessionStorage.removeItem(pendingKey); setPending(''); } catch { /* optional bookmark */ } };
    const events = ['depo:credentials-cleared', 'depo:credentials-changed', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, reset));
    return () => { request.current?.abort(); events.forEach(event => window.removeEventListener(event, reset)); };
  }, [bookmark]);
  useEffect(() => {
    if (!runId || (run && !['queued', 'running', 'interrupted'].includes(run.status))) return;
    let stopped = false, timer;
    const poll = async () => {
      if (document.hidden) { timer = setTimeout(poll, 3000); return; }
      const controller = new AbortController(); request.current = controller;
      try {
        const response = await agenticClient.get(url(`goals/${encodeURIComponent(runId)}`), { signal: controller.signal });
        if (!stopped && !controller.signal.aborted) {
          if (response.data?.run_id !== runId) throw new Error('Retained task reference mismatch; reload task history.');
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
  useEffect(()=>{onRunChange?.(run);},[run,onRunChange]);
  const active = runId && (!run || ['queued', 'running', 'interrupted'].includes(run.status));
  return <section aria-label="Read-only goal investigation" className={compact?'read-goal-compact':'depo-panel'}>
    {!compact&&<><h4>Investigate a goal with the agent</h4>
    <p>The agent uses the configured model to plan subtasks, uses registered read tools, and revises its approach after a failed read. The plan and observations are retained in PostgreSQL across restarts. This mode cannot publish or modify the knowledge graph.</p></>}
    {!resumeOnly && <button type="button" disabled={disabled || busy || active || !agent || !task?.trim()} onClick={async () => {
      request.current?.abort(); const controller = new AbortController(); request.current = controller;
      setBusy(true); setError('');
      try {
        const submission = pending || crypto.randomUUID(); setPending(submission);
        try { sessionStorage.setItem(pendingKey, submission); } catch { /* memory still retains the submission */ }
        const response = await agenticClient.post(url(`agents/${encodeURIComponent(agent)}/goals`), { task: task.trim(), context: selectedContext, submission_id: submission }, { signal: controller.signal });
        if (typeof response.data?.run_id !== 'string' || !response.data.run_id.startsWith('goal-')) throw new Error('The service did not return a retained task reference. Recover the same submission before starting another.');
        if (!controller.signal.aborted) { setRun(response.data); setRunId(response.data.run_id); try { sessionStorage.setItem(bookmark, response.data.run_id); sessionStorage.removeItem(pendingKey); setPending(''); window.dispatchEvent(new CustomEvent('depo:page-task-updated')); } catch { /* optional bookmark */ } }
      } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
      finally { if (!controller.signal.aborted) setBusy(false); }
    }}>{busy ? 'Starting investigation…' : pending ? 'Recover submitted investigation' : startLabel}</button>}
    {runId && <button type="button" onClick={() => { request.current?.abort(); setRunId(''); setRun(null); try { sessionStorage.removeItem(bookmark); } catch {} }}>Close investigation view (task is retained)</button>}
    {active && <button type="button" disabled={busy} onClick={async () => {
      request.current?.abort(); const controller = new AbortController(); request.current = controller;
      setBusy(true); setError('');
      try {
        const response = await agenticClient.post(url(`goals/${encodeURIComponent(runId)}/cancel`), {}, { signal: controller.signal });
        if (!controller.signal.aborted) setRun(response.data);
      } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
      finally { if (!controller.signal.aborted) setBusy(false); }
    }}>Cancel investigation</button>}
    {error && <p role="alert">{error}</p>}
    {run && <TaskProgress run={run} kind="goal" />}

  </section>;
}
