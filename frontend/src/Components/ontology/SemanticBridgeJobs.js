import BridgeDecisionReview from './BridgeDecisionReview';
import SemanticSupport from '../SemanticSupport';
import GovernedLearningPanel from './GovernedLearningPanel';
import DecisionPolicyAssessment from '../DecisionPolicyAssessment';
import MappingReviewTable from './MappingReviewTable';
import { getCredentialProfile, publicationRecoveryScope } from '../../services/serviceAuth';
import React, { useEffect, useRef, useState } from 'react';
import { bridgeApi } from '../../services/bridgeApi';
import agenticAPI from '../../services/agenticApi';
import { bridgeReviewPayload } from '../../services/bridgeReviewPayload';
import WorkflowTaskPanel from '../WorkflowTaskPanel';
import WorkflowRecoveryActions from '../WorkflowRecoveryActions';
import { PrimaryButton, TextField } from '../../ui/ix';
import './SemanticBridgeJobs.css';


class PreviewInputError extends Error {}

// User-facing error copy: each message names the action the user can take.
function errorMessage(error) {
  if (error instanceof PreviewInputError) return error.message;
  const detail = error.response?.data?.detail;
  if ([401, 403].includes(error.response?.status)) return 'Access to this workflow was rejected. Reconnect in Admin > API access, then retry. Do not start another run until the current outcome is verified.';
  if (typeof detail === 'string') return detail;
  // FastAPI validation details contain objects (and can contain submitted input).
  // Never render the raw response or echo credential-bearing input fields.
  if (error.response?.status === 422) return 'Some inputs are invalid. Check the selected source and ontology, then retry.';
  return 'The request was interrupted. Refresh the job status, then retry.';
}

export default function SemanticBridgeJobs({ ontologyId, importTaskId, manualMappings = [], sourceUnavailable = false, api = bridgeApi }) {
  const [preview, setPreview] = useState(null);
  const [learningOpen,setLearningOpen]=useState(false);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [resumeId, setResumeId] = useState('');
  const [agentReport, setAgentReport] = useState(null);
  const [policyReport, setPolicyReport] = useState(null);
  const [automationStage, setAutomationStage] = useState('idle');
  const [automationRun, setAutomationRun] = useState(null);
  const [recoveryWorkflowId, setRecoveryWorkflowId] = useState('');
  const generation = useRef(0);
  const activeOperation = useRef(null);
  const mappingsKey = JSON.stringify(manualMappings);
  const [credentialRevision, setCredentialRevision] = useState(0);
  const [candidateOffset, setCandidateOffset] = useState(0);
  const workflowKey = `bridge-workflow:${publicationRecoveryScope()}:${ontologyId}:${importTaskId}:${mappingsKey}:${candidateOffset}`;
  useEffect(() => setCandidateOffset(0), [ontologyId, importTaskId, mappingsKey]);
  useEffect(() => {
    const invalidate = () => setCredentialRevision(value => value + 1);
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired','depo:session-replaced'];
    events.forEach(event => window.addEventListener(event, invalidate));
    return () => events.forEach(event => window.removeEventListener(event, invalidate));
  }, []);
  useEffect(() => {
    generation.current += 1;
    activeOperation.current = null;
    setPreview(null); setJob(null); setMessage(''); setBusy(false); setAgentReport(null);
    setPolicyReport(null); setAutomationStage('idle'); setAutomationRun(null);
    try {
      setResumeId(sessionStorage.getItem(`bridge-preview:${ontologyId}:${importTaskId}`) || '');
      const id = sessionStorage.getItem(workflowKey);
      if (id) { setAutomationRun({run_id:id === 'submission-unconfirmed' ? '' : id,status:'unknown'}); setAutomationStage('Saved workflow; refresh its result'); }
    } catch { setResumeId(''); }
    return () => { generation.current += 1; };
  }, [ontologyId, importTaskId, mappingsKey, credentialRevision, workflowKey]);

  const invoke = async (operation) => {
    if (activeOperation.current !== null) return;
    const current = generation.current;
    const operationId = Symbol('bridge-operation');
    activeOperation.current = operationId;
    setBusy(true); setMessage('');
    try { await operation(() => current === generation.current); }
    catch (error) { if (current === generation.current) setMessage(errorMessage(error)); }
    finally {
      if (activeOperation.current === operationId) activeOperation.current = null;
      if (current === generation.current) setBusy(false);
    }
  };
  const adoptPreview = (value) => {
    if (!value || value.kind !== 'preview' || value.ontology_id !== ontologyId || value.import_task_id !== importTaskId) {
      throw new PreviewInputError('Preview belongs to another source or ontology. Select its inputs first.');
    }
    if (!value.job_id || !value.publication_job_id || !Array.isArray(value.candidates) ||
        value.candidates.some(candidate => !candidate || !candidate.candidate_id)) {
      throw new PreviewInputError('Saved preview is incomplete. Create a new preview before review.');
    }
    setPreview(value); setJob(null); setResumeId(value.job_id);
    try { sessionStorage.setItem(`bridge-preview:${ontologyId}:${importTaskId}`, value.job_id); } catch { /* optional recovery aid */ }
  };
  const refresh = async (isCurrent) => {
    let response;
    try { response = await api.status(preview.publication_job_id, getCredentialProfile('GRAPH_READ_TOKEN')); }
    catch (error) {
      if (error.response?.status === 404 && isCurrent()) {
        setJob(null);
        setMessage('No publication exists yet. Review the mappings in Change Control.');
        return;
      }
      throw error;
    }
    if (!isCurrent()) return;
    setJob(response.data);
  };
  useEffect(() => {
    const id = new URLSearchParams(window.location.hash.split('?')[1] || '').get('bridge_preview');
    if (!id || !ontologyId || !importTaskId) return;
    let stopped = false;
    const stamp = generation.current;
    api.status(id, getCredentialProfile('GRAPH_READ_TOKEN')).then(response => {
      if (!stopped && stamp === generation.current) adoptPreview(response.data);
    }).catch(error => { if (!stopped && stamp === generation.current) setMessage(errorMessage(error)); });
    return () => { stopped = true; };
  }, [ontologyId, importTaskId, api, credentialRevision]);
  const adoptAutomation = value => {
    if (typeof value?.run_id !== 'string' || !value.run_id || !['queued','running','paused','completed','failed','timed_out','cancelled','interrupted','recoverable'].includes(value.status) ||
        (value.workflow_id && value.workflow_id !== 'bridge-validated-automation') ||
        (automationRun?.run_id && value.run_id !== automationRun.run_id)) throw new PreviewInputError('Invalid automation run. Inspect agent telemetry before retrying.');
    const traces = value.traces || [];
    if (value.allowed_actions !== undefined && (!Array.isArray(value.allowed_actions) || value.allowed_actions.some(action => !['pause','resume','cancel'].includes(action)))) throw new PreviewInputError('Invalid workflow controls. Refresh the retained run.');
    if (!Array.isArray(traces) || traces.some(trace => !trace || typeof trace !== 'object' || Array.isArray(trace))) throw new PreviewInputError('Invalid workflow evidence. Refresh the saved run.');
    const saved = traces.find(trace => trace.tool_id === 'bridge.mapping.preview' && trace.status === 'completed')?.result;
    if (saved && (saved.kind !== 'preview' || saved.ontology_id !== ontologyId || saved.import_task_id !== importTaskId || !saved.job_id || !saved.publication_job_id || !Array.isArray(saved.candidates) || saved.candidates.some(row => !row?.candidate_id))) {
      throw new PreviewInputError('Workflow preview belongs to another source or ontology, or is incomplete.');
    }
    const policy = traces.find(trace => trace.tool_id === 'bridge.mapping.evaluate' && trace.status === 'completed')?.result;
    if (policy && (!Array.isArray(policy.decisions) || !Array.isArray(policy.accepted_ids) ||
        !Number.isInteger(policy.held_count) || policy.held_count < 0 ||
        policy.decisions.some(item => !item || typeof item.candidate_id !== 'string' || !['hold','publish'].includes(item.decision) ||
          !Array.isArray(item.reasons) || item.reasons.some(reason => typeof reason !== 'string')))) {
      throw new PreviewInputError('Validation results are invalid. Refresh the retained workflow, then retry.');
    }
    setAutomationRun(value);
    try { sessionStorage.setItem(workflowKey, value.run_id); } catch { /* optional recovery */ }
    if (saved) adoptPreview(saved);
    if (policy && Array.isArray(policy.decisions) && Array.isArray(policy.accepted_ids)) setPolicyReport(policy);
    const published = traces.find(trace => trace.tool_id === 'bridge.mapping.publish_automatic' && trace.status === 'completed')?.result;
    if (published?.status === 'published') { setJob(published); }
    setAutomationStage(value.status === 'completed' ? published?.status === 'held' ? 'Completed: all mappings held' : 'Completed' : `Workflow ${value.status}; refresh to inspect progress`);
  };
  useEffect(() => {
    if (!automationRun?.run_id || !['unknown','queued','running','paused'].includes(automationRun.status) || !api.automationStatus) return;
    let timer; let stopped = false;
    const stamp = generation.current;
    const poll = async () => {
      if (stopped || stamp !== generation.current) return;
      if (document.hidden || activeOperation.current !== null) { timer = setTimeout(poll,3000); return; }
      try {
        const response = await api.automationStatus(automationRun.run_id);
        if (!stopped && stamp === generation.current) adoptAutomation(response.data);
      } catch (error) {
        if (!stopped && stamp === generation.current) setMessage(errorMessage(error));
        if ([401,403,404].includes(error.response?.status)) return;
      }
      if (!stopped) timer = setTimeout(poll,3000);
    };
    timer = setTimeout(poll,3000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [automationRun?.run_id, automationRun?.status, api, credentialRevision, workflowKey]);
  const hasAutomationAccess = Boolean(getCredentialProfile('AGENTIC_APPROVAL_TOKEN') && getCredentialProfile('GRAPH_READ_TOKEN'));
  return <section className="depo-bridge-review" aria-label="Governed Semantic Bridge jobs">
    <div className="bridge-primary">
    {(!ontologyId || !importTaskId) && <p role="status">Select both an imported instance and a target ontology to enable agent review and mapping.</p>}
    <PrimaryButton disabled={sourceUnavailable || busy || !!automationRun || !ontologyId || !importTaskId || !hasAutomationAccess} onClick={() => invoke(async current => {
      const response = await api.preview(ontologyId, importTaskId, {approval_token:getCredentialProfile('AGENTIC_APPROVAL_TOKEN')}, manualMappings, candidateOffset);
      if (current()) adoptPreview(response.data);
    })}>Prepare mappings</PrimaryButton>
    </div>
    {automationRun && <details className="mapping-run-controls"><summary>Workflow status, controls and policy · {automationRun?.status || 'Ready to start'}</summary>
    {automationRun && <div role="status">Workflow: {automationRun.run_id} · {automationRun.status}
      <button type="button" className="bridge-action" disabled={busy || !automationRun.run_id || !api.automationStatus} onClick={() => invoke(async current => {
        const response = await api.automationStatus(automationRun.run_id);
        if (current()) adoptAutomation(response.data);
      })}>Refresh automation result</button>
    </div>}
    {automationRun?.allowed_actions?.filter(action => ['pause','resume','cancel'].includes(action)).map(action => <button type="button" key={action} disabled={busy} onClick={() => invoke(async current => {
      await agenticAPI.controlWorkflow(automationRun.run_id,action);
      const response = await api.automationStatus(automationRun.run_id);
      if (current()) adoptAutomation(response.data);
    })}>{action}</button>)}
    <WorkflowRecoveryActions key={automationRun?.run_id} run={automationRun} disabled={busy} onRefresh={async () => {
      const response = await api.automationStatus(automationRun.run_id); adoptAutomation(response.data);
    }} />
    {['completed', 'failed', 'cancelled', 'timed_out'].includes(automationRun?.status) && !automationRun.reconciliation_required && <button type="button" disabled={busy} onClick={() => {
      try { sessionStorage.removeItem(workflowKey); } catch { /* optional recovery */ }
      setAutomationRun(null); setAutomationStage('idle'); setPreview(null); setJob(null); setPolicyReport(null);
    }}>Prepare another mapping run</button>}
    {automationRun?.status === 'unknown' && !automationRun.run_id && <p role="alert">The response was interrupted. Check recent workflows in Agent telemetry, then retry before starting another publication.</p>}
    {automationRun?.status === 'unknown' && !automationRun.run_id && <details className="bridge-recovery"><summary>Recovery: look up a retained workflow</summary>
      <div><TextField label="Recover mapping workflow ID" value={recoveryWorkflowId} onValueChange={setRecoveryWorkflowId} />
      <button type="button" className="bridge-action" disabled={busy || !recoveryWorkflowId.trim()} onClick={() => invoke(async current => {
        const response = await api.automationStatus(recoveryWorkflowId.trim());
        if (current()) adoptAutomation(response.data);
      })}>Inspect retained mapping workflow</button></div></details>}
    </details>}
    {message && <p role="alert">{message}</p>}
    {!hasAutomationAccess && <p>Connect read and governed agent access in Admin to prepare mappings.</p>}
    {automationStage !== 'idle' && <p role="status" aria-live="polite">{busy ? automationStage : message ? 'Status unavailable. The background workflow may still be running; reconnect and inspect its retained result before retrying.' : automationStage}</p>}
    {preview && <MappingReviewTable compact candidates={preview.candidates} decisions={policyReport?.decisions || []} />}
    <SemanticSupport report={policyReport?.semantic_support}/>{policyReport && <details><summary>What was checked</summary>
      <DecisionPolicyAssessment report={policyReport.decision_policy} />
      {policyReport.governance && <p>This check covers the suggested classes for each imported item. It does not check every rule, confirm that two items are the same, or approve anything. Source import: {policyReport.governance.provenance?.import_task_id}. No changes were made to the vocabulary.</p>}
    </details>}
    <WorkflowTaskPanel concise workflowId="ontology-review-and-bridge-plan" inputs={{ ontology_id: ontologyId, import_task_id: importTaskId }} label="Run ontology agent review" disabled={sourceUnavailable || busy || !ontologyId || !importTaskId || !agenticAPI.isConfigured()} onResult={run => setAgentReport(bridgeReviewPayload({ steps: run.traces.map(trace => ({ result: trace.result })) }))} />
    {agentReport && <details><summary>View compatibility assessment</summary><BridgeDecisionReview report={agentReport} /></details>}
    <details className="depo-saved-recommendation bridge-recovery"><summary>Recovery: resume a saved preview</summary>
    <TextField label="Saved preview ID" value={resumeId} onValueChange={setResumeId} />
    <button type="button" className="bridge-action" disabled={busy || !resumeId.trim() || !ontologyId || !importTaskId} onClick={() => invoke(async current => {
      const result = await api.status(resumeId.trim(), getCredentialProfile('GRAPH_READ_TOKEN'));
      if (!current()) return;
      adoptPreview(result.data);
      // Keep approval disabled until publication recovery succeeds or returns 404.
      setJob({ job_id: result.data.publication_job_id, status: 'unknown', approved_ids: [] });
      try {
        const publication = await api.status(result.data.publication_job_id, getCredentialProfile('GRAPH_READ_TOKEN'));
        if (current()) { setJob(publication.data); }
      } catch (error) {
        if (error.response?.status !== 404) throw error;
        if (current()) setJob(null);
      }
    })}>Load preview</button>
    </details>
    {preview && <>
      {Number.isInteger(preview.partition?.next_offset) && <button type="button" disabled={busy} onClick={() => setCandidateOffset(preview.partition.next_offset)}>Prepare next mapping batch</button>}
      {preview.partition && <p>Batch starts at candidate {preview.partition.offset + 1}; {preview.partition.total_candidates} candidates in this source.</p>}
      <p>{preview.candidates.length} mapping candidates</p>
      {preview.recommendation_summary && <p role="status">{preview.recommendation_summary.total} mapping recommendations; {preview.recommendation_summary.eligible} eligible for review.</p>}
      <a className="bridge-action" href={`#/change-control?source=bridges&view=workflows&record_source=bridges&record=${encodeURIComponent(preview.job_id)}&return_to=${encodeURIComponent(`#/ontology?view=alignment&mode=instance&target=${encodeURIComponent(ontologyId)}&import_task_id=${encodeURIComponent(importTaskId)}&bridge_preview=${encodeURIComponent(preview.job_id)}`)}`}>Review CR / CO in Change Control</a>
      <button type="button" className="bridge-action" disabled={busy || !preview.publication_job_id} onClick={() => invoke(refresh)}>Refresh publication status</button>
      <button type="button" className="bridge-action" disabled={busy} onClick={() => invoke(async current => {
        const result = await api.artifact(job?.status === 'published' ? job.job_id : preview.job_id, getCredentialProfile('GRAPH_READ_TOKEN'));
        if (!current()) return;
        const url = URL.createObjectURL(result.data); const link = document.createElement('a');
        link.href = url; link.download = 'semantic-bridge-job.json'; link.click(); URL.revokeObjectURL(url);
      })}>Download evidence</button>
    {job && <div role="status"><strong>Publication: {job.status}</strong><div>{job.job_id}</div>
        {job.agent_run_id && <p>Publication agent run: {job.agent_run_id}</p>}
        {job.receipt && <p>{job.receipt.applied_links} mappings published. Approved by {job.receipt.approved_by}.</p>}
        {job.error && <p>{job.error}</p>}
      </div>}
    </>}
    {job?.status === 'published' && <p role="status">{job.receipt?.applied_links || 0} mappings published to knowledge graph. {policyReport?.held_count || 0} mappings held and unchanged. Publication: {job.job_id}.</p>}
    <details onToggle={event=>setLearningOpen(event.currentTarget.open)}><summary>Learning from reviewed mappings</summary>
      {learningOpen&&<GovernedLearningPanel key={`${ontologyId}:${importTaskId}`} ontologyId={ontologyId} importTaskId={importTaskId} publication={job} preview={preview}/>}
    </details>
  </section>;
}
