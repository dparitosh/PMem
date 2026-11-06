import { useEffect, useRef, useState } from 'react';
import { agenticClient } from '../../../services/agenticApi';
import { buildSemanticServiceUrl } from '../../../config';
import { pageTaskContext, taskBookmarkKey } from '../../../services/pageTasks';
import { apiErrorMessage } from '../../../utils/apiErrorMessage';
import { createSubmissionId } from '../../../utils/submissionId';
import {wasBrowserSessionExpired} from '../../../services/serviceAuth';

function checkedGoal(data, expectedId) {
  const record=value=>value&&typeof value==='object'&&!Array.isArray(value);
  const text=value=>value==null||typeof value==='string';
  if(!record(data)||typeof data.run_id!=='string'||!data.run_id.startsWith('goal-')||
    (expectedId&&data.run_id!==expectedId)||
    !['queued','running','interrupted','completed','failed','cancelled','blocked','timed_out','budget_exhausted','needs_input'].includes(data.status)||
    (data.missing_fields!=null&&(!Array.isArray(data.missing_fields)||data.missing_fields.some(field=>typeof field!=='string')))||
    !text(data.goal)||!text(data.result?.summary)||
    (data.observations!=null&&(!Array.isArray(data.observations)||data.observations.some(item=>!record(item)||!text(item.message)||!text(item.error_message))))||
    (data.plans!=null&&(!Array.isArray(data.plans)||data.plans.some(plan=>!record(plan)||!Array.isArray(plan.subtasks)||plan.subtasks.some(step=>typeof step!=='string'))))) {
    throw new Error('The agent returned an invalid investigation record. Check service versions and recover the retained task before starting another.');
  }
  return data;
}

export default function useReadGoal({ agent, task, context, storageKey, initialRunId = '', onRunChange }) {
  const selectedContext = { ...(context || {}), ...pageTaskContext(context || {}) };
  const bookmark = storageKey || taskBookmarkKey(agent, selectedContext, task);
  const pendingKey = bookmark + ':pending';
  const [pending, setPending] = useState('');
  const [accessRejected, setAccessRejected] = useState(false);
  const [pollPaused, setPollPaused] = useState(false);
  const [pollRevision, setPollRevision] = useState(0);
  const [run, setRun] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState(() => { try { return initialRunId || sessionStorage.getItem(bookmark) || ''; } catch { return ''; } });
  // User actions and status reads have independent cancellation ownership.
  const request = useRef(null);
  const polling = useRef(null);
  const url = path => buildSemanticServiceUrl('agentic', `/api/v1/${path}`);
  useEffect(() => {
    request.current?.abort(); request.current = null; polling.current?.abort(); setRun(null); setError(''); setBusy(false); setPollPaused(false);
    try { setRunId(initialRunId || sessionStorage.getItem(bookmark) || ''); setPending(sessionStorage.getItem(pendingKey) || ''); }
    catch { setRunId(initialRunId); setPending(''); }
  }, [bookmark, initialRunId]);
  useEffect(() => {
    const reset = event => {
      const expired=event.type==='depo:session-expired'||wasBrowserSessionExpired();
      setPollPaused(false);
      setAccessRejected(expired); request.current?.abort(); request.current=null; polling.current?.abort();setRun(null);setBusy(false);
      setError(expired?'Access expired. Reconnect to recover the retained investigation.':'');
      if(event.type==='depo:credentials-cleared'){
        setRunId('');setPending('');
        try{sessionStorage.removeItem(bookmark);sessionStorage.removeItem(pendingKey);}catch{/* optional bookmark */}
      }
      // Expiry/reconnect retains references only. The server reauthorizes every
      // read and recovery; credential replacement never resubmits a task.
    };
    const rejected = () => { setAccessRejected(true); request.current?.abort(); request.current=null; polling.current?.abort(); setRun(null); setBusy(false); setError('API access was rejected. Revalidate access before continuing; the submitted investigation is retained.'); };
    const verified = () => { setAccessRejected(false); setError(''); setPollPaused(false); setPollRevision(value => value + 1); };
    const events = ['depo:credentials-cleared', 'depo:credentials-changed', 'depo:session-expired','depo:session-replaced'];
    events.forEach(event => window.addEventListener(event, reset));
    window.addEventListener('depo:access-rejected',rejected);window.addEventListener('depo:access-verified',verified);
    return () => { request.current?.abort(); polling.current?.abort(); events.forEach(event => window.removeEventListener(event, reset));window.removeEventListener('depo:access-rejected',rejected);window.removeEventListener('depo:access-verified',verified); };
  }, [bookmark]);
  useEffect(() => {
    if (accessRejected || pollPaused || busy || !runId || (run && !['queued', 'running', 'interrupted'].includes(run.status))) return;
    let stopped = false, timer, failures = 0;
    const poll = async () => {
      if (document.hidden) { timer = setTimeout(poll, 3000); return; }
      const controller = new AbortController(); polling.current = controller;
      try {
        const response = await agenticClient.get(url(`goals/${encodeURIComponent(runId)}`), { signal: controller.signal });
        if (!stopped && !controller.signal.aborted && !request.current) {
          checkedGoal(response.data,runId);
          failures = 0;
          setRun(response.data); setError('');
          if (['queued', 'running', 'interrupted'].includes(response.data.status)) timer = setTimeout(poll, 3000);
        }
      } catch (failure) {
        if (!stopped && !controller.signal.aborted && !request.current) {
          const status = failure?.response?.status;
          const permanent = [400,401,403,404,410,422].includes(status) || !failure?.response && !failure?.request && !failure?.code;
          if (permanent || ++failures >= 3) {
            setPollPaused(true);
            setError(`${apiErrorMessage(failure)} Status checks paused. Refresh status after resolving access or service availability; closing this view does not cancel or resubmit the retained task.`);
          } else {
            setError(apiErrorMessage(failure)); timer = setTimeout(poll, 10000);
          }
        }
      }
    };
    poll();
    return () => { stopped = true; clearTimeout(timer); polling.current?.abort(); };
  }, [runId, run?.status, busy, accessRejected, pollPaused, pollRevision]);
  useEffect(()=>{onRunChange?.(run);},[run,onRunChange]);
  const active = runId && (!run || ['queued', 'running', 'interrupted'].includes(run.status));
  const start = async () => {
      if (request.current || accessRejected) return;
      polling.current?.abort(); const controller = new AbortController(); request.current = controller;
      setBusy(true); setError(''); setPollPaused(false);
      try {
        const submission = pending || createSubmissionId(); setPending(submission);
        try { sessionStorage.setItem(pendingKey, submission); } catch { /* memory still retains the submission */ }
        const response = await agenticClient.post(url(`agents/${encodeURIComponent(agent)}/goals`), { task: task.trim(), context: selectedContext, submission_id: submission }, { signal: controller.signal });
        checkedGoal(response.data);
        if (!controller.signal.aborted) { setRun(response.data); setRunId(response.data.run_id); try { sessionStorage.setItem(bookmark, response.data.run_id); sessionStorage.removeItem(pendingKey); setPending(''); window.dispatchEvent(new CustomEvent('depo:page-task-updated')); } catch { /* optional bookmark */ } }
      } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
      finally { if (request.current === controller) { request.current = null; if (!controller.signal.aborted) setBusy(false); } }
  };
  const cancel = async () => {
      if (request.current || accessRejected) return;
      polling.current?.abort(); const controller = new AbortController(); request.current = controller;
      setBusy(true); setError('');
      try {
        const response = await agenticClient.post(url(`goals/${encodeURIComponent(runId)}/cancel`), {}, { signal: controller.signal });
        checkedGoal(response.data,runId);
        if (!controller.signal.aborted) setRun(response.data);
      } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
      finally { if (request.current === controller) { request.current = null; if (!controller.signal.aborted) setBusy(false); } }
  };
  const close = () => { request.current?.abort(); request.current = null; polling.current?.abort(); setBusy(false); setPollPaused(false); setRunId(''); setRun(null); try { sessionStorage.removeItem(bookmark); } catch { /* optional bookmark */ } };
  const refresh = () => { setPollPaused(false); setPollRevision(value => value + 1); };
  return { run, error, busy, pending, runId, active, accessRejected, pollPaused, refresh, start, cancel, close };
}
