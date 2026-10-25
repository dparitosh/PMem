import { useEffect, useRef, useState } from 'react';
import { agenticClient } from '../../../services/agenticApi';
import { buildSemanticServiceUrl } from '../../../config';
import { pageTaskContext, taskBookmarkKey } from '../../../services/pageTasks';
import { apiErrorMessage } from '../../../utils/apiErrorMessage';

export default function useReadGoal({ agent, task, context, storageKey, initialRunId = '', onRunChange }) {
  const selectedContext = { ...(context || {}), ...pageTaskContext(context || {}) };
  const bookmark = storageKey || taskBookmarkKey(agent, selectedContext, task);
  const pendingKey = bookmark + ':pending';
  const [pending, setPending] = useState('');
  const [run, setRun] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState(() => { try { return initialRunId || sessionStorage.getItem(bookmark) || ''; } catch { return ''; } });
  // User actions and status reads have independent cancellation ownership.
  const request = useRef(null);
  const polling = useRef(null);
  const url = path => buildSemanticServiceUrl('agentic', `/api/v1/${path}`);
  useEffect(() => {
    request.current?.abort(); request.current = null; polling.current?.abort(); setRun(null); setError(''); setBusy(false);
    try { setRunId(initialRunId || sessionStorage.getItem(bookmark) || ''); setPending(sessionStorage.getItem(pendingKey) || ''); }
    catch { setRunId(initialRunId); setPending(''); }
  }, [bookmark, initialRunId]);
  useEffect(() => {
    const reset = () => { request.current?.abort(); request.current = null; polling.current?.abort(); setRun(null); setRunId(''); setError(''); setBusy(false); try { sessionStorage.removeItem(bookmark); sessionStorage.removeItem(pendingKey); setPending(''); } catch { /* optional bookmark */ } };
    const events = ['depo:credentials-cleared', 'depo:credentials-changed', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, reset));
    return () => { request.current?.abort(); polling.current?.abort(); events.forEach(event => window.removeEventListener(event, reset)); };
  }, [bookmark]);
  useEffect(() => {
    if (busy || !runId || (run && !['queued', 'running', 'interrupted'].includes(run.status))) return;
    let stopped = false, timer;
    const poll = async () => {
      if (document.hidden) { timer = setTimeout(poll, 3000); return; }
      const controller = new AbortController(); polling.current = controller;
      try {
        const response = await agenticClient.get(url(`goals/${encodeURIComponent(runId)}`), { signal: controller.signal });
        if (!stopped && !controller.signal.aborted && !request.current) {
          if (response.data?.run_id !== runId) throw new Error('Retained task reference mismatch; reload task history.');
          setRun(response.data); setError('');
          if (['queued', 'running', 'interrupted'].includes(response.data.status)) timer = setTimeout(poll, 3000);
        }
      } catch (failure) {
        if (!stopped && !controller.signal.aborted && !request.current) { setError(apiErrorMessage(failure)); timer = setTimeout(poll, 10000); }
      }
    };
    poll();
    return () => { stopped = true; clearTimeout(timer); polling.current?.abort(); };
  }, [runId, run?.status, busy]);
  useEffect(()=>{onRunChange?.(run);},[run,onRunChange]);
  const active = runId && (!run || ['queued', 'running', 'interrupted'].includes(run.status));
  const start = async () => {
      if (request.current) return;
      polling.current?.abort(); const controller = new AbortController(); request.current = controller;
      setBusy(true); setError('');
      try {
        const submission = pending || crypto.randomUUID(); setPending(submission);
        try { sessionStorage.setItem(pendingKey, submission); } catch { /* memory still retains the submission */ }
        const response = await agenticClient.post(url(`agents/${encodeURIComponent(agent)}/goals`), { task: task.trim(), context: selectedContext, submission_id: submission }, { signal: controller.signal });
        if (typeof response.data?.run_id !== 'string' || !response.data.run_id.startsWith('goal-')) throw new Error('The service did not return a retained task reference. Recover the same submission before starting another.');
        if (!controller.signal.aborted) { setRun(response.data); setRunId(response.data.run_id); try { sessionStorage.setItem(bookmark, response.data.run_id); sessionStorage.removeItem(pendingKey); setPending(''); window.dispatchEvent(new CustomEvent('depo:page-task-updated')); } catch { /* optional bookmark */ } }
      } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
      finally { if (request.current === controller) { request.current = null; if (!controller.signal.aborted) setBusy(false); } }
  };
  const cancel = async () => {
      if (request.current) return;
      polling.current?.abort(); const controller = new AbortController(); request.current = controller;
      setBusy(true); setError('');
      try {
        const response = await agenticClient.post(url(`goals/${encodeURIComponent(runId)}/cancel`), {}, { signal: controller.signal });
        if (response.data?.run_id !== runId) throw new Error('Retained task reference mismatch; reload task history.');
        if (!controller.signal.aborted) setRun(response.data);
      } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
      finally { if (request.current === controller) { request.current = null; if (!controller.signal.aborted) setBusy(false); } }
  };
  const close = () => { request.current?.abort(); request.current = null; polling.current?.abort(); setBusy(false); setRunId(''); setRun(null); try { sessionStorage.removeItem(bookmark); } catch { /* optional bookmark */ } };
  return { run, error, busy, pending, runId, active, start, cancel, close };
}
