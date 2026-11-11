import SemanticSupport from '../SemanticSupport';
import GovernedLearningPanel from './GovernedLearningPanel';
import DecisionPolicyAssessment from '../DecisionPolicyAssessment';
import { matchScore } from './MappingExplanation';
import MappingReviewTable from './MappingReviewTable';
import { getCredentialProfile, publicationRecoveryScope } from '../../services/serviceAuth';
import React, { useEffect, useRef, useState } from 'react';
import { bridgeApi } from '../../services/bridgeApi';
import agenticAPI from '../../services/agenticApi';
import { bridgeReviewPayload } from '../../services/bridgeReviewPayload';
import WorkflowTaskPanel from '../WorkflowTaskPanel';
import WorkflowRecoveryActions from '../WorkflowRecoveryActions';
import { confirmedSubmissionRejection } from '../../services/workflowSubmission';
import { PrimaryButton, SecondaryButton, TextField, CheckboxField, DataTable } from '../../ui/ix';
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
  if (error.response?.status === 422) return 'Some inputs are invalid. Check the selected source and approval fields, then retry.';
  return 'The request was interrupted. Refresh the job status, then retry.';
}

export default function SemanticBridgeJobs({ ontologyId, importTaskId, manualMappings = [], sourceUnavailable = false, api = bridgeApi }) {
  const [preview, setPreview] = useState(null);
  const [learningOpen,setLearningOpen]=useState(false);
  const [job, setJob] = useState(null);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [actor, setActor] = useState('');
  const [resumeId, setResumeId] = useState('');
  const [confirmed, setConfirmed] = useState(false);
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
    setPreview(null); setJob(null); setSelected([]); setMessage(''); setBusy(false); setAgentReport(null);
    setConfirmed(false);
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
    setPreview(value); setSelected([]); setJob(null); setConfirmed(false); setResumeId(value.job_id);
    try { sessionStorage.setItem(`bridge-preview:${ontologyId}:${importTaskId}`, value.job_id); } catch { /* optional recovery aid */ }
  };
  const refresh = async (isCurrent) => {
    let response;
    try { response = await api.status(preview.publication_job_id, getCredentialProfile('GRAPH_READ_TOKEN')); }
    catch (error) {
      if (error.response?.status === 404 && isCurrent()) {
        setJob(null); setSelected([]); setConfirmed(false);
        setMessage('No publication exists yet. Select and review mappings before publishing.');
        return;
      }
      throw error;
    }
    if (!isCurrent()) return;
    setJob(response.data); setSelected(response.data.approved_ids || []);
    if (response.data.status === 'published') setConfirmed(false);
  };
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
    if (published?.status === 'published') { setJob(published); setSelected(published.approved_ids || []); }
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
  const fixedSelection = !!job;
  const hasApproval = Boolean(actor.trim() && getCredentialProfile('AGENTIC_APPROVAL_TOKEN'));
  const hasAutomationAccess = Boolean(getCredentialProfile('AGENTIC_APPROVAL_TOKEN') && getCredentialProfile('GRAPH_READ_TOKEN'));
  const canPublish = !sourceUnavailable && hasApproval && preview && selected.length > 0 && confirmed && !busy && (!job || ['approved', 'retryable'].includes(job.status));
  return <section className="depo-bridge-review" aria-label="Governed Semantic Bridge jobs">
    <div className="bridge-primary">
    {(!ontologyId || !importTaskId) && <p role="status">Select both an imported instance and a target ontology to enable agent review and mapping.</p>}
    <p className="mapping-review__note">Propose, validate, then publish. Mappings that fail validation stay held.</p>
    <ol className="depo-action-steps bridge-stages" aria-label="Mapping automation stages">
      <li><strong>Propose</strong><span>Create saved mapping evidence</span></li>
      <li><strong>Validate</strong><span>Check validation, confidence and ambiguity</span></li>
      <li><strong>Publish</strong><span>Publish policy-approved mappings</span></li>
    </ol>
    <p className="mapping-review__note">Starting a run authorizes publication of mappings that pass policy validated-only-v1; individual approval is not required for those mappings.</p>
    <PrimaryButton disabled={sourceUnavailable || busy || !!automationRun || !ontologyId || !importTaskId || !hasAutomationAccess || !api.automate} onClick={() => invoke(async current => {
      const identity = {approved_by: actor.trim() || 'bridge-automation', approval_token:getCredentialProfile('AGENTIC_APPROVAL_TOKEN')};
      setAutomationStage('Proposing, validating and publishing mappings…');
      try {
        try { sessionStorage.setItem(workflowKey, 'submission-unconfirmed'); } catch { /* recovery remains in memory */ }
        const response = await api.automate(ontologyId, importTaskId, identity, manualMappings, candidateOffset);
        if (current()) adoptAutomation(response.data);
      } catch (error) {
        const id = error.response?.headers?.['x-depo-run-id'];
        if (current()) {
          if (confirmedSubmissionRejection(error)) {
            setAutomationRun(null); setAutomationStage('Task rejected; check inputs and access');
            try { sessionStorage.removeItem(workflowKey); } catch {}
          } else setAutomationRun({run_id:id || '',status:'unknown'});
          if (id) try { sessionStorage.setItem(workflowKey, id); } catch { /* optional recovery */ }
        }
        throw error;
      }
    })}>Run automated mapping and publish</PrimaryButton>
    </div>
    <details className="mapping-run-controls" open={!preview}><summary>Workflow status, controls and policy · {automationRun?.status || 'Ready to start'}</summary>
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
    {Number.isInteger(preview?.partition?.next_offset) && ((automationRun?.status === 'completed' && !automationRun.reconciliation_required) || (!automationRun && job?.status === 'published')) && <button type="button" disabled={busy} onClick={() => setCandidateOffset(preview.partition.next_offset)}>Prepare next mapping batch</button>}
    {preview?.partition && <p>Batch starts at candidate {preview.partition.offset + 1}; {preview.partition.total_candidates} total candidates. Each batch retains its own approval and publication receipt.</p>}
    {['completed', 'failed', 'cancelled', 'timed_out'].includes(automationRun?.status) && !automationRun.reconciliation_required && <button type="button" disabled={busy} onClick={() => {
      try { sessionStorage.removeItem(workflowKey); } catch { /* optional recovery */ }
      setAutomationRun(null); setAutomationStage('idle'); setPreview(null); setJob(null); setPolicyReport(null); setSelected([]);
    }}>Prepare another mapping run</button>}
    {automationRun?.status === 'unknown' && !automationRun.run_id && <p role="alert">The response was interrupted. Check recent workflows in Agent telemetry, then retry before starting another publication.</p>}
    {automationRun?.status === 'unknown' && !automationRun.run_id && <details className="bridge-recovery"><summary>Recovery: look up a retained workflow</summary>
      <div><TextField label="Recover mapping workflow ID" value={recoveryWorkflowId} onValueChange={setRecoveryWorkflowId} />
      <button type="button" className="bridge-action" disabled={busy || !recoveryWorkflowId.trim()} onClick={() => invoke(async current => {
        const response = await api.automationStatus(recoveryWorkflowId.trim());
        if (current()) adoptAutomation(response.data);
      })}>Inspect retained mapping workflow</button></div></details>}
    </details>
    {message && <p role="alert">{message}</p>}
    {!hasAutomationAccess && <p>Connect read and governed agent access in Admin to run automation.</p>}
    {automationStage !== 'idle' && <p role="status" aria-live="polite">{busy ? automationStage : message ? 'Status unavailable. The background workflow may still be running; reconnect and inspect its retained result before retrying.' : automationStage}</p>}
    {preview && <MappingReviewTable candidates={preview.candidates} decisions={policyReport?.decisions || []} />}
    <SemanticSupport report={policyReport?.semantic_support}/>{policyReport && <details><summary>What was checked</summary>
      <DecisionPolicyAssessment report={policyReport.decision_policy} />
      {policyReport.governance && <p>This check covers the suggested classes for each imported item. It does not check every rule, confirm that two items are the same, or approve anything. Source import: {policyReport.governance.provenance?.import_task_id}. No changes were made to the vocabulary.</p>}
    </details>}
    <WorkflowTaskPanel workflowId="ontology-review-and-bridge-plan" inputs={{ ontology_id: ontologyId, import_task_id: importTaskId }} label="Run ontology agent review" disabled={sourceUnavailable || busy || !ontologyId || !importTaskId || !agenticAPI.isConfigured()} onResult={run => setAgentReport(bridgeReviewPayload({ steps: run.traces.map(trace => ({ result: trace.result })) }))} />
    <p>Optional: the agent explains how the imported data lines up with the ontology. It does not publish anything. Its findings appear below when it finishes.</p>
    {!agenticAPI.isConfigured() && <small>Enable the Agentic service to run ontology intake and review.</small>}
    {agentReport && <div role="status" className="bridge-agent-report">
      <strong>Ontology agent review:</strong> {agentReport.steps?.length || 0} steps completed. Advisory findings; mapping publication uses the separate validation and approval workflow.
      {agentReport.steps?.[1]?.result?.issues?.length ? ` ${agentReport.steps[1].result.issues.length} structural issue(s) require review.` : Array.isArray(agentReport.steps?.[1]?.result?.issues) ? ' No structural issues reported.' : ' Structural review results are unavailable.'}
      <p>{agentReport.steps?.at(-1)?.result?.alignment_candidates?.length || 0} exact-name candidate(s) found. These are review evidence only; use a saved Bridge preview to publish mappings.</p>
      <p>{agentReport.steps?.at(-1)?.result?.unmatched_count || 0} unmatched sources; {agentReport.steps?.at(-1)?.result?.ambiguous_count || 0} ambiguous sources.</p>
      {(agentReport.steps?.at(-1)?.result?.alignment_items || []).map((item, index) => <div key={`${item.source}:${index}`}><strong>{item.source}</strong>: {item.status}. Checks requiring review: {(item.unresolved_checks || []).join(', ')}</div>)}
      {(agentReport.steps?.at(-1)?.result?.alignment_candidates || []).length > 0 && <ul>
        {agentReport.steps.at(-1).result.alignment_candidates.slice(0, 20).map((candidate, index) => <li key={`${candidate.source}:${candidate.target_iri}:${index}`}>
          {candidate.source} → {candidate.target_iri} ({candidate.target_type}; {candidate.evidence})
        </li>)}
      </ul>}
      {agentReport.steps?.at(-1)?.result?.candidate_limit_reached && <p>Candidate search was limited. Narrow the ontology or review the full Bridge preview.</p>}
      {agentReport.steps?.at(-1)?.result?.llm && <div>
        <strong>Model recommendation (review only):</strong>
        {agentReport.steps.at(-1).result.llm.review && <div>
          {agentReport.steps.at(-1).result.llm.review.questions?.map((question, index) => <div key={index}>
            <p>{question.question}</p><p>Evidence IRIs: {question.evidence_iris?.join(', ') || 'No citation supplied'}</p>
          </div>)}
          <p>Limitations: {agentReport.steps.at(-1).result.llm.review.limitations}</p>
          {agentReport.steps.at(-1).result.llm.review.prompt_details && <details><summary>Prompt details used for this review</summary><pre className="bridge-prompt-details">{JSON.stringify(agentReport.steps.at(-1).result.llm.review.prompt_details, null, 2)}</pre></details>}
        </div>}
        <p>{agentReport.steps.at(-1).result.llm.text || (agentReport.steps.at(-1).result.llm.enabled ? 'Model unavailable; deterministic review evidence remains available.' : 'Model recommendations are disabled.')}</p>
      </div>}
    </div>}
    <details><summary>Advanced: manual review and approval</summary>
    <details><summary>Who approves publication?</summary>
      <p>The approver is the person authorised to accept these mappings. The mapping workflow prepares and checks the operation; it cannot approve on your behalf. Connect governed credentials in Admin.</p>
      <TextField label="Approver" value={actor} onValueChange={setActor} />
    </details>
    {!hasApproval && <p>Enter an approver and connect governed agent access in Admin before preview or publication.</p>}
    <SecondaryButton className="bridge-action" disabled={sourceUnavailable || busy || !ontologyId || !importTaskId || !hasApproval} onClick={() => invoke(async current => {
      const result = await api.preview(ontologyId, importTaskId, {approved_by: actor.trim(), approval_token: getCredentialProfile('AGENTIC_APPROVAL_TOKEN')}, manualMappings, candidateOffset);
      if (current()) adoptPreview(result.data);
    })}>Create preview</SecondaryButton>

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
        if (current()) { setJob(publication.data); setSelected(publication.data.approved_ids || []); }
      } catch (error) {
        if (error.response?.status !== 404) throw error;
        if (current()) setJob(null);
      }
    })}>Load preview</button>
    </details>
    {preview && <>
      <p><strong>Preview:</strong> {preview.job_id} · {preview.candidates.length} candidates · {selected.length} selected</p>
      <p>Approvals are bound to this source and ontology snapshot. Source or manual mapping changes require a new preview.</p>
      {preview.agent_run_id && <p>Preview agent run: {preview.agent_run_id}</p>}
      {preview.recommendation_summary && <p role="status">{preview.recommendation_summary.total} mapping recommendations; {preview.recommendation_summary.eligible} eligible for review. Recommendations do not grant publication approval.</p>}
      <div className="bridge-candidates">
        <DataTable
          caption="Candidate mappings"
          columns={[
            { key: 'approve', label: 'Approve' },
            { key: 'source', label: 'Source' },
            { key: 'target', label: 'Ontology target' },
            { key: 'validation', label: 'Validation' },
            { key: 'score', label: 'Match score' },
          ]}
          rows={preview.candidates}
          rowKey={candidate => candidate.candidate_id}
          empty={<span>No candidates found. Check the imported data and ontology before creating another preview.</span>}
          renderCell={(candidate, column) => {
            const sourceName = candidate.source_label || candidate.source_term || candidate.import_row_key;
            switch (column.key) {
              case 'approve':
                return <CheckboxField
                  label={`Approve ${sourceName} to ${candidate.ontology_term}`}
                  disabled={busy || fixedSelection || !candidate.eligible}
                  checked={selected.includes(candidate.candidate_id)}
                  onCheckedChange={checked => {
                    setConfirmed(false);
                    setSelected(ids => checked ? [...ids, candidate.candidate_id] : ids.filter(id => id !== candidate.candidate_id));
                  }}
                />;
              case 'source': return sourceName;
              case 'target': return `${candidate.ontology_term} (${candidate.target_ontology_type})`;
              case 'validation': return <>{candidate.eligible ? 'Reviewable' : 'Invalid'}{[...(candidate.validation_errors || []), ...(candidate.validation_warnings || [])].map((text, index) => <div key={index}>{text}</div>)}</>;
              default: return matchScore(candidate);
            }
          }}
        />
      </div>
      <label><input type="checkbox" aria-label="Confirm reviewed mappings" checked={confirmed} disabled={busy || !selected.length || job?.status === 'published'} onChange={e => setConfirmed(e.target.checked)} /> I reviewed these {selected.length} mappings and approve their publication.</label><br />
      <PrimaryButton className="bridge-action" disabled={!canPublish} onClick={() => invoke(async current => {
        // Freeze the selection immediately; response loss must not allow editing.
        setJob({ job_id: preview.publication_job_id, status: 'publishing', approved_ids: selected });
        try {
          const result = await api.publish(preview.job_id, selected, { approved_by: actor.trim(), approval_token: getCredentialProfile('AGENTIC_APPROVAL_TOKEN') });
          if (current()) { setJob(result.data); setConfirmed(false); }
        } finally { /* Shared credentials remain managed in Admin. */ }
      })}>{busy ? 'Working…' : job ? 'Retry same publication' : 'Publish approved mappings'}</PrimaryButton>
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
    </details>
    {job?.status === 'published' && <p role="status">{job.receipt?.applied_links || 0} mappings published to knowledge graph. {policyReport?.held_count || 0} mappings held and unchanged. Publication: {job.job_id}.</p>}
    <details onToggle={event=>setLearningOpen(event.currentTarget.open)}><summary>Learning from reviewed mappings</summary>
      {learningOpen&&<GovernedLearningPanel key={`${ontologyId}:${importTaskId}`} ontologyId={ontologyId} importTaskId={importTaskId} publication={job} preview={preview}/>}
    </details>
  </section>;
}
