import React, { useEffect, useRef, useState } from 'react';
import { IxButton } from '@siemens/ix-react';
import { agenticClient } from '../services/agenticApi';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';

export default function AgentControlPanel() {
  const [runId, setRunId] = useState('');
  const [run, setRun] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [llmHealth, setLlmHealth] = useState(null);
  const [llmError, setLlmError] = useState('');
  const [llmBusy, setLlmBusy] = useState(false);
  const llmRequest = useRef(null);
  const request = useRef(null);
  useEffect(() => {
    const clear = () => { llmRequest.current?.abort(); setLlmHealth(null); setLlmError(''); setLlmBusy(false); request.current?.abort(); setRun(null); setMessage(''); setError(''); setBusy(false); };
    window.addEventListener('depo:credentials-changed', clear);
    window.addEventListener('depo:credentials-cleared', clear);
    return () => { llmRequest.current?.abort(); request.current?.abort(); window.removeEventListener('depo:credentials-changed', clear); window.removeEventListener('depo:credentials-cleared', clear); };
  }, []);
  async function operate(action) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(''); setMessage('');
    try {
      const supervisor = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
      if (action && !supervisor) throw new Error('Test and apply AGENTIC_APPROVAL_TOKEN in Admin, or connect a session with governed write access.');
      const url = buildSemanticServiceUrl('agentic', `/api/v1/workflow-runs/${encodeURIComponent(runId.trim())}`);
      const options = { signal: controller.signal, headers: supervisor ? { Authorization: `Bearer ${supervisor}` } : {} };
      if (action) {
        const result = await agenticClient.post(`${url}/control`, { action }, options);
        if (!controller.signal.aborted) setMessage(`${result.data.action} requested. It takes effect at the next tool boundary.`);
      }
      const response = await agenticClient.get(url, options);
      if (!controller.signal.aborted) setRun(response.data);
    } catch (failure) {
      if (!controller.signal.aborted) setError(typeof failure.response?.data?.detail === 'string' ? failure.response.data.detail : failure.message);
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className="depo-panel" aria-label="Agent workflow controls">
    <div className="depo-panel__header"><h3>Agent workflow controls</h3></div>
    <IxButton disabled={llmBusy} onClick={async () => {
      llmRequest.current?.abort(); const controller = new AbortController(); llmRequest.current = controller;
      setLlmBusy(true); setLlmHealth(null); setLlmError('');
      try {
        const response = await agenticClient.get(buildSemanticServiceUrl('agentic', '/api/v1/llm/health'), { signal: controller.signal, timeout: 10000 });
        if (!controller.signal.aborted) setLlmHealth(response.data);
      } catch (failure) { if (!controller.signal.aborted) setLlmError(failure.response?.data?.detail || 'Cannot reach agentic diagnostics. Check service connectivity and read credentials.'); }
      finally { if (!controller.signal.aborted) setLlmBusy(false); }
    }}>Check offline Ollama</IxButton>
    {llmHealth && <p role="status">Ollama: {llmHealth.status}. Model: {llmHealth.model || 'not selected'}. {llmHealth.action} Ontology agents: {llmHealth.ontology_agent_enabled ? 'enabled' : 'disabled'}. Companion generation: {llmHealth.companion_enabled ? 'enabled' : 'disabled'}.</p>}
    {llmError && <p role="alert">{typeof llmError === 'string' ? llmError : 'LLM diagnostic failed.'}</p>}
    <p>Inspect a workflow run ID from agent telemetry. Pause and cancel take effect between tools; they do not interrupt an active tool or undo completed writes. The original execution deadline still applies.</p>
    <p>These controls apply to multi-step agent workflows. Standalone ontology intake, review and bridge planning remain single operations.</p>
    <label htmlFor="agent-control-run">Workflow run ID</label>
    <input style={{ color: 'var(--ui-text)', background: 'var(--ui-surface)', border: '1px solid var(--ui-border)', padding: 8, margin: 8 }} id="agent-control-run" value={runId} onChange={event => { request.current?.abort(); setBusy(false); setRun(null); setMessage(''); setError(''); setRunId(event.target.value); }} placeholder="run-…" />
    <IxButton disabled={busy || !runId.trim()} onClick={() => operate()}>Inspect / refresh</IxButton>
    {['pause', 'resume', 'cancel'].map(action => <IxButton key={action} disabled={busy || run?.status !== 'running'} onClick={() => operate(action)}>{action}</IxButton>)}
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    {run && <p>Run status: {run.status}. Requested control: {run.control?.action || 'none'}. Completed steps: {run.traces?.filter(trace => trace.status === 'completed').length || 0}.</p>}
  </section>;
}
