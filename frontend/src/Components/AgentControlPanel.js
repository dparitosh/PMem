import React, { useEffect, useRef, useState } from 'react';
import { IxButton } from '@siemens/ix-react';
import { agenticClient } from '../services/agenticApi';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';

export default function AgentControlPanel() {
  const [runId, setRunId] = useState('');
  const [run, setRun] = useState(null);
  const [runKind, setRunKind] = useState('workflow');
  const [recentRuns, setRecentRuns] = useState([]);
  const [listBusy, setListBusy] = useState(false);
  const [listError, setListError] = useState('');
  const listRequest = useRef(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reconciliationEvidence, setReconciliationEvidence] = useState('');
  const [reconciliationResult, setReconciliationResult] = useState('');
  const [executorStopped, setExecutorStopped] = useState(false);
  const [compensationPlan, setCompensationPlan] = useState(null);
  const [compensationReason, setCompensationReason] = useState('');
  const [llmHealth, setLlmHealth] = useState(null);
  const [llmCapabilities, setLlmCapabilities] = useState(null);
  const [llmError, setLlmError] = useState('');
  const [llmBusy, setLlmBusy] = useState(false);
  const llmRequest = useRef(null);
  const request = useRef(null);
  useEffect(() => {
    const clear = () => { setCompensationPlan(null); setCompensationReason(''); listRequest.current?.abort(); setRecentRuns([]); setListBusy(false); setListError(''); llmRequest.current?.abort(); setLlmHealth(null); setLlmCapabilities(null); setLlmError(''); setLlmBusy(false); request.current?.abort(); setRun(null); setMessage(''); setError(''); setBusy(false); setReconciliationEvidence(''); setReconciliationResult(''); setExecutorStopped(false); };
    const inspectAgent = event => { clear(); setRunKind(event.detail.execution_kind === 'workflow' ? 'workflow' : 'agent'); setRunId(event.detail.run_id); setRun(event.detail); };
    window.addEventListener('depo:inspect-agent-run', inspectAgent);
    window.addEventListener('depo:credentials-changed', clear);
    window.addEventListener('depo:credentials-cleared', clear);
    return () => { listRequest.current?.abort(); llmRequest.current?.abort(); request.current?.abort(); window.removeEventListener('depo:inspect-agent-run', inspectAgent); window.removeEventListener('depo:credentials-changed', clear); window.removeEventListener('depo:credentials-cleared', clear); };
  }, []);
  useEffect(() => {
    if (!runId.trim() || !run || busy || !['running','queued','dispatching','paused'].includes(run.status)) return;
    let active = true, controller = null;
    const interval = window.setInterval(async () => {
      if (document.hidden || controller) return;
      controller = new AbortController();
      try {
        const supervisor = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
        const response = await agenticClient.get(buildSemanticServiceUrl('agentic', `/api/v1/${runKind === 'workflow' ? 'workflow-runs' : 'runs'}/${encodeURIComponent(runId.trim())}`),
          {signal:controller.signal, timeout:15000, headers:runKind === 'workflow' && supervisor ? {Authorization:`Bearer ${supervisor}`} : {}});
        if (active) { setRun(response.data); setError(''); }
      } catch (failure) { if (active) setError(typeof failure.response?.data?.detail === 'string' ? failure.response.data.detail : 'Workflow refresh failed; displayed state may be stale.'); }
      finally { controller = null; }
    }, 3000);
    return () => { active = false; window.clearInterval(interval); controller?.abort(); };
  }, [runId, runKind, !!run, run?.status, busy]);
  async function loadRecentRuns() {
    listRequest.current?.abort(); const controller = new AbortController(); listRequest.current = controller;
    setListBusy(true); setListError('');
    const supervisor = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
    const options = {signal:controller.signal, timeout:15000};
    try {
      const results = await Promise.allSettled([
        agenticClient.get(buildSemanticServiceUrl('agentic', '/api/v1/workflow-runs?limit=50'), {...options, headers:supervisor ? {Authorization:`Bearer ${supervisor}`} : {}}),
        agenticClient.get(buildSemanticServiceUrl('agentic', '/api/v1/observability/runs?limit=50'), options),
      ]);
      if (controller.signal.aborted) return;
      const rows = [];
      results.forEach((result, index) => {
        if (result.status === 'fulfilled' && Array.isArray(result.value.data?.runs)) {
          rows.push(...result.value.data.runs.filter(item => index === 0 || (item.operation !== 'workflow' && !item.workflow_run_id))
            .map(item => ({...item, kind:index === 0 ? 'workflow' : 'agent'})));
        }
      });
      setRecentRuns(rows);
      if (results.some(result => result.status === 'rejected' || !Array.isArray(result.value?.data?.runs))) setListError('Some run lists are unavailable. Check service versions and read/supervisor access.');
    } catch (failure) { if (!controller.signal.aborted) setListError(failure.message || 'Run lists are unavailable.'); }
    finally { if (!controller.signal.aborted) setListBusy(false); }
  }
  async function operate(action, selectedId = runId.trim(), kind = runKind) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(''); setMessage('');
    try {
      const supervisor = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
      if (action && kind !== 'workflow') throw new Error('Standalone executions do not support workflow controls.');
      if (action && !supervisor) throw new Error('Test and apply AGENTIC_APPROVAL_TOKEN in Admin, or connect a session with governed write access.');
      const url = buildSemanticServiceUrl('agentic', `/api/v1/${kind === 'workflow' ? 'workflow-runs' : 'runs'}/${encodeURIComponent(selectedId)}`);
      const options = { signal: controller.signal, timeout:15000, headers: kind === 'workflow' && supervisor ? { Authorization: `Bearer ${supervisor}` } : {} };
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
  async function recoverOrReconcile(outcome) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(''); setMessage('');
    try {
      const supervisor = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
      const read = getCredentialProfile('GRAPH_READ_TOKEN');
      if (!supervisor) throw new Error('Connect governed agent supervision access in Admin.');
      if (!outcome && !read) throw new Error('Connect graph read access before recovering a workflow.');
      const productReceipt = outcome === 'receipt' && run?.pending_step?.tool_id === 'data.product.publish';
      if (productReceipt && !read) throw new Error('Connect graph read access before verifying a product publication receipt.');
      const payload = { approved_by: 'agent-supervisor', approval_token: supervisor };
      if (outcome) {
        payload.outcome = outcome;
        payload.executor_stopped = executorStopped;
        payload.evidence = reconciliationEvidence.trim();
        if (outcome !== 'receipt' && !payload.evidence) throw new Error('Record the downstream receipt or verification evidence first.');
        if (outcome === 'completed') payload.result = JSON.parse(reconciliationResult);
      }
      const url = buildSemanticServiceUrl('agentic', `/api/v1/workflow-runs/${encodeURIComponent(runId.trim())}`);
      await agenticClient.post(`${url}/${outcome === 'receipt' ? 'reconcile-receipt' : outcome ? 'reconcile' : 'recover'}`, payload,
        { signal: controller.signal, headers: { Authorization: `Bearer ${outcome === 'receipt' ? (productReceipt ? read : read || supervisor) : outcome ? supervisor : read}` } });
      const response = await agenticClient.get(url, { signal: controller.signal, headers: { Authorization: `Bearer ${supervisor}` } });
      if (!controller.signal.aborted) { setRun(response.data); setMessage(outcome ? 'Reconciliation evidence recorded.' : response.data.status === 'completed' ? 'Workflow recovery finished.' : `Workflow recovery accepted. Current status: ${response.data.status || 'unverified'}.`); }
    } catch (failure) {
      if (!controller.signal.aborted) setError(typeof failure.response?.data?.detail === 'string' ? failure.response.data.detail : failure.message);
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function compensate(sequence) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(''); setMessage('');
    try {
      const supervisor = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
      if (!supervisor) throw new Error('Connect agent supervision approval in Admin.');
      const url = buildSemanticServiceUrl('agentic', `/api/v1/workflow-runs/${encodeURIComponent(runId.trim())}`);
      const options = {signal:controller.signal, timeout:60000, headers:{Authorization:`Bearer ${supervisor}`}};
      if (sequence == null) {
        const response = await agenticClient.get(`${url}/compensation-plan`,options);
        if (!controller.signal.aborted) setCompensationPlan(response.data);
      } else {
        const response = await agenticClient.post(`${url}/compensate`,{sequence,reason:compensationReason.trim(),approved_by:'agent-supervisor',approval_token:supervisor},options);
        if (!controller.signal.aborted) setMessage(`Compensation for step ${sequence}: ${response.data.status}. Original artifacts and history remain retained.`);
      }
    } catch (failure) { if (!controller.signal.aborted) setError(typeof failure.response?.data?.detail === 'string' ? failure.response.data.detail : failure.message); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  const controlActions = runKind !== 'workflow' ? [] : run?.allowed_actions ??
    (run?.status === 'running' && run.control?.action !== 'cancel' ? (run.control?.action === 'pause' ? ['resume', 'cancel'] : ['pause', 'cancel']) : []);
  const reconcileAllowed = runKind === 'workflow' && (run?.reconcile_allowed ?? (run?.pending_step?.mutates && ['failed', 'interrupted', 'timed_out'].includes(run.status)));
  const verifyExecutor = run?.executor_stop_verification_required ?? run?.status === 'running';
  return <section className="depo-panel depo-workflow-controls" aria-label="Agent workflow controls">
    <div className="depo-panel__header"><h3>Agent workflow controls</h3></div>
    <div className="depo-panel__body">
    <IxButton disabled={llmBusy} onClick={async () => {
      llmRequest.current?.abort(); const controller = new AbortController(); llmRequest.current = controller;
      setLlmBusy(true); setLlmHealth(null); setLlmCapabilities(null); setLlmError('');
      try {
        const response = await agenticClient.get(buildSemanticServiceUrl('agentic', '/api/v1/llm/health'), { signal: controller.signal, timeout: 10000 });
        if (!controller.signal.aborted) setLlmHealth(response.data);
      } catch (failure) { if (!controller.signal.aborted) setLlmError(failure.response?.data?.detail || 'Cannot reach agentic diagnostics. Check service connectivity and read credentials.'); }
      finally { if (!controller.signal.aborted) setLlmBusy(false); }
    }}>Check Ollama configuration</IxButton>
    <IxButton disabled={llmBusy} onClick={async () => {
      llmRequest.current?.abort(); const controller = new AbortController(); llmRequest.current = controller;
      setLlmBusy(true); setLlmCapabilities(null); setLlmError('');
      try {
        const supervisor = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
        if (!supervisor) throw new Error('Connect agent supervision access before probing Ollama capabilities.');
        const response = await agenticClient.post(buildSemanticServiceUrl('agentic', '/api/v1/llm/probe'),
          {approved_by:'agent-supervisor',approval_token:supervisor}, {signal:controller.signal,timeout:370000,headers:{Authorization:`Bearer ${supervisor}`}});
        if (!controller.signal.aborted) setLlmCapabilities(response.data);
      } catch (failure) { if (!controller.signal.aborted) setLlmError(typeof failure.response?.data?.detail === 'string' ? failure.response.data.detail : failure.message); }
      finally { if (!controller.signal.aborted) setLlmBusy(false); }
    }}>Verify Ollama capabilities</IxButton>
    <p>Capability verification sends up to three small inference requests. It does not execute a tool.</p>
    {llmCapabilities && <div role="status"><p>Capability model: {llmCapabilities.model || 'unverified'}.</p><p>Generation: {llmCapabilities.generation || 'unverified'}. Structured output: {llmCapabilities.structured_outputs || 'unverified'}. Native tool calling: {llmCapabilities.native_tool_calling || 'unverified'}.</p></div>}
    {llmHealth && <div role="status"><p>Ollama: <strong>{llmHealth.status}</strong>. Model: {llmHealth.model || 'not selected'}.</p><p>{llmHealth.action}</p>{llmHealth.endpoint && <p>{llmHealth.discovery_enabled === false ? 'Configured generation endpoint' : 'Checked endpoint'}: {llmHealth.endpoint}.{llmHealth.probe_timeout_seconds != null && <> Probe deadline: {llmHealth.probe_timeout_seconds} seconds.</>}</p>}<p>Ontology agents: {llmHealth.ontology_agent_enabled ? 'enabled' : 'disabled'}. Companion generation: {llmHealth.companion_enabled ? 'enabled' : 'disabled'}.</p></div>}
    {llmError && <p role="alert">{typeof llmError === 'string' ? llmError : 'LLM diagnostic failed.'}</p>}
    <p>Select a recent workflow or enter its ID. Status refreshes every three seconds while this page is visible. Pause and cancel take effect between tools; they do not interrupt an active tool or undo completed writes. The original execution deadline still applies.</p>
    <p>These controls apply to multi-step agent workflows. Standalone ontology intake, review and bridge planning remain single operations.</p>
    <div className="depo-workflow-run-picker">
      <IxButton disabled={listBusy} onClick={loadRecentRuns}>{listBusy ? 'Loading runs…' : 'Load recent runs'}</IxButton>
      <label>Recent executions<select aria-label="Recent executions" value="" disabled={busy || listBusy} onChange={event => {
        const value = recentRuns[Number(event.target.value)]; if (!value) return;
        request.current?.abort(); setCompensationPlan(null); setCompensationReason(''); setRun(null); setMessage(''); setError(''); setReconciliationEvidence(''); setReconciliationResult(''); setExecutorStopped(false);
        setRunKind(value.kind); setRunId(value.run_id);
        operate(undefined, value.run_id, value.kind);
      }}><option value="">Select a workflow or standalone agent run</option>{recentRuns.map((value, index) => <option key={`${value.kind}:${value.run_id}`} value={index}>{value.kind === 'workflow' ? 'Workflow' : 'Standalone'} · {value.workflow_id || value.agent_id || value.operation || value.run_id} · {value.status}</option>)}</select></label>
      {listError && <p role="alert">{listError}</p>}
    </div>
    {runKind === 'agent' && <p>Standalone execution: {runId}. Workflow pause, resume and cancel do not apply to this run.</p>}
    <label htmlFor="agent-control-run">Workflow run ID</label>
    <input style={{ color: 'var(--ui-text)', background: 'var(--ui-surface)', border: '1px solid var(--ui-border)', padding: 8, margin: 8 }} id="agent-control-run" value={runKind === 'workflow' ? runId : ''} onChange={event => { request.current?.abort(); setRunKind('workflow'); setCompensationPlan(null); setCompensationReason(''); setBusy(false); setRun(null); setMessage(''); setError(''); setReconciliationEvidence(''); setReconciliationResult(''); setExecutorStopped(false); setRunId(event.target.value); }} placeholder="run-…" />
    <IxButton disabled={busy || !runId.trim()} onClick={() => operate()}>Inspect / refresh</IxButton>
    {['pause', 'resume', 'cancel'].map(action => <IxButton key={action} disabled={busy || !controlActions.includes(action)} onClick={() => operate(action)}>{action}</IxButton>)}
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    {run && <p>Run status: {run.execution_state || run.status}. Requested control: {run.control?.action || 'none'}. {run.control?.acknowledged_at && <>Acknowledged at tool boundary: {run.control.acknowledged_at}. </>}Completed steps: {run.traces?.filter(trace => trace.status === 'completed').length || 0}.</p>}
    {runKind === 'agent' && run && <details><summary>Standalone execution details</summary><pre>{JSON.stringify(run, null, 2)}</pre></details>}
    {runKind === 'workflow' && run && <div className="depo-workflow-evidence">
      <p>Original deadline: {run.deadline_at || 'Not available'}. Last execution activity: {run.last_activity_at || run.updated_at || 'Not available'}.</p>
      {run.pending_step && <p>Current tool: {run.pending_step.tool_id}. Attempt: {run.pending_step.attempt}. {run.pending_step.mutates ? 'May write downstream data.' : 'Read operation.'}</p>}
      {run.execution_mode && <p>{run.execution_mode === 'worker' ? 'Durable worker execution can recover read-only interruptions after restart. Uncertain writes require receipt reconciliation.' : 'Execution continues independently of a browser disconnect. Recovery after a service restart requires supervisor review.'} Completed writes are retained.</p>}
      {run.traces?.length > 0 && <details><summary>Step results and receipt evidence</summary><pre>{JSON.stringify(run.traces, null, 2)}</pre></details>}
    </div>}
    {runKind === 'workflow' && run && (run.recover_allowed ?? (['failed', 'interrupted', 'recoverable'].includes(run.status) && !run.reconciliation_required && !run.pending_step?.mutates)) &&
      <IxButton disabled={busy || !runId.trim() || Date.parse(run.deadline_at) <= Date.now()} onClick={() => recoverOrReconcile()}>Recover remaining steps</IxButton>}
    {reconcileAllowed && <div className="depo-workflow-reconciliation">
      <p>Verify the downstream write before recovery. Completed writes will be retained.</p>
      {verifyExecutor && <label><input type="checkbox" checked={executorStopped} onChange={event => setExecutorStopped(event.target.checked)} />I verified that the original executor has stopped</label>}
      <label>Downstream verification evidence<textarea value={reconciliationEvidence} onChange={event => setReconciliationEvidence(event.target.value)} maxLength={4000} /></label>
      <label>Completed write result (JSON)<textarea value={reconciliationResult} onChange={event => setReconciliationResult(event.target.value)} /></label>
      <IxButton disabled={busy || !reconciliationEvidence.trim() || (verifyExecutor && !executorStopped)} onClick={() => recoverOrReconcile('not_applied')}>Record verified unapplied write</IxButton>
      <IxButton disabled={busy || !reconciliationEvidence.trim() || !reconciliationResult.trim() || (verifyExecutor && !executorStopped)} onClick={() => recoverOrReconcile('completed')}>Record completed write receipt</IxButton>
      {['data.product.publish','bridge.mapping.publish'].includes(run.pending_step?.tool_id) && <IxButton disabled={busy || (verifyExecutor && !executorStopped)} onClick={() => recoverOrReconcile('receipt')}>Verify downstream receipt automatically</IxButton>}
    </div>}
    {runKind === 'workflow' && run && !['running','queued'].includes(run.status) && !run.pending_step && !run.reconciliation_required && <section className="depo-workflow-reconciliation" aria-label="Approved compensation">
      <IxButton disabled={busy} onClick={() => compensate()}>Review reversible operations</IxButton>
      {compensationPlan && <>
        <p>Compensation changes lifecycle state through an approved service operation. It does not delete original artifacts or history.</p>
        <label>Compensation reason<textarea maxLength={4000} value={compensationReason} disabled={busy} onChange={event => setCompensationReason(event.target.value)} /></label>
        {compensationPlan.actions?.map(action => <div key={action.sequence}><p>Step {action.sequence}: {action.product_version}. {action.effect}</p><IxButton disabled={busy || !compensationReason.trim()} onClick={() => compensate(action.sequence)}>Approve revocation of {action.product_version}</IxButton></div>)}
        {compensationPlan.unsupported?.map(action => <p key={action.sequence}>Step {action.sequence} ({action.tool_id}): {action.reason}.</p>)}
        {!compensationPlan.actions?.length && <p>No reversible operation is defined for the completed steps.</p>}
      </>}
    </section>}
    </div>
  </section>;
}
