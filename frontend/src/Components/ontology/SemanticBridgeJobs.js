import { getCredentialProfile } from '../../services/serviceAuth';
import React, { useEffect, useRef, useState } from 'react';
import { bridgeApi } from '../../services/bridgeApi';
import agenticAPI from '../../services/agenticApi';


class PreviewInputError extends Error {}

function errorMessage(error) {
  if (error instanceof PreviewInputError) return error.message;
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  // FastAPI validation details contain objects (and can contain submitted input).
  // Never render the raw response or echo credential-bearing input fields.
  if (error.response?.status === 422) return 'Invalid request. Check the selected inputs and approval fields.';
  return 'Request interrupted. Refresh job status before retrying.';
}

export default function SemanticBridgeJobs({ ontologyId, importTaskId, api = bridgeApi }) {
  const [preview, setPreview] = useState(null);
  const [job, setJob] = useState(null);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [actor, setActor] = useState('');
  const [resumeId, setResumeId] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [agentReport, setAgentReport] = useState(null);
  const generation = useRef(0);
  const activeOperation = useRef(null);
  useEffect(() => {
    generation.current += 1;
    activeOperation.current = null;
    setPreview(null); setJob(null); setSelected([]); setMessage(''); setBusy(false); setAgentReport(null);
    setConfirmed(false);
    try { setResumeId(sessionStorage.getItem(`bridge-preview:${ontologyId}:${importTaskId}`) || ''); } catch { setResumeId(''); }
    return () => { generation.current += 1; };
  }, [ontologyId, importTaskId]);

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
    if (value.kind !== 'preview' || value.ontology_id !== ontologyId || value.import_task_id !== importTaskId) {
      throw new PreviewInputError('Preview belongs to another source or ontology. Select its inputs first.');
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
  const fixedSelection = !!job;
  const canPublish = preview && selected.length > 0 && confirmed && !busy && (!job || ['approved', 'retryable'].includes(job.status));
  const buttonStyle = { padding: '8px 12px', marginRight: 8, marginTop: 8 };
  return <section aria-label="Governed Semantic Bridge jobs" style={{ background: 'var(--ui-surface, #fff)', color: 'var(--ui-text, #1f2933)', padding: 16, border: '1px solid var(--ui-border, #ccd5df)', borderRadius: 8, marginTop: 16 }}>
    <h3>Preview → review → publish</h3>
    <p>Create a saved preview, select valid mappings, then approve publication. Nothing is selected automatically.</p>
    <details><summary>Approval identity</summary>
      <p>Manage and validate service credentials in Admin. Supply the approver identity for reviewed publication here.</p>
      <label>Approver <input aria-label="Approver" value={actor} onChange={e => setActor(e.target.value)} /></label>{' '}
    </details>
    <button type="button" style={buttonStyle} disabled={busy || !ontologyId || !importTaskId} onClick={() => invoke(async current => {
      const result = await api.preview(ontologyId, importTaskId, getCredentialProfile('GRAPH_READ_TOKEN'));
      if (current()) adoptPreview(result.data);
    })}>Create preview</button>
    <button type="button" style={buttonStyle} disabled={busy || !ontologyId || !importTaskId || !agenticAPI.isConfigured()} onClick={() => invoke(async current => {
      const result = await agenticAPI.orchestrateOntology({ workflow_id: 'ontology_review', ontology_id: ontologyId, import_task_id: importTaskId }, authOptions(getCredentialProfile('GRAPH_READ_TOKEN')));
      if (current()) setAgentReport(result.data);
    })}>Run ontology agent review</button>
    {!agenticAPI.isConfigured() && <small>Enable the Agentic service to run ontology intake and review.</small>}
    {agentReport && <div role="status" style={{ marginTop: 8, padding: 8, background: 'var(--ui-surface)', color: 'var(--ui-text)', border: '1px solid var(--ui-border)' }}>
      <strong>Ontology agent review:</strong> {agentReport.steps?.length || 0} steps completed; publication requires human approval.
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
    </div>}
    <label>Saved preview ID <input aria-label="Saved preview ID" value={resumeId} onChange={e => setResumeId(e.target.value)} /></label>
    <button type="button" style={buttonStyle} disabled={busy || !resumeId.trim() || !ontologyId || !importTaskId} onClick={() => invoke(async current => {
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
    {message && <p role="alert">{message}</p>}
    {preview && <>
      <p><strong>Preview:</strong> {preview.job_id} · {preview.candidates.length} candidates · {selected.length} selected</p>
      <p>Approvals are bound to this source and ontology snapshot. Changes require a new preview. Saved manual mapping drafts elsewhere on this page are not published by this job.</p>
      <div style={{ maxHeight: 360, overflow: 'auto' }}><table style={{ width: '100%', textAlign: 'left' }}>
        <thead><tr><th>Approve</th><th>Source</th><th>Ontology target</th><th>Validation</th><th>Confidence</th></tr></thead>
        <tbody>{preview.candidates.map(candidate => <tr key={candidate.candidate_id}>
          <td><input type="checkbox" aria-label={`Approve ${candidate.source_label || candidate.source_term || candidate.import_row_key} to ${candidate.ontology_term}`} disabled={busy || fixedSelection || !candidate.eligible}
            checked={selected.includes(candidate.candidate_id)} onChange={e => {
              setConfirmed(false);
              setSelected(ids => e.target.checked ? [...ids, candidate.candidate_id] : ids.filter(id => id !== candidate.candidate_id));
            }} /></td>
          <td>{candidate.source_label || candidate.source_term || candidate.import_row_key}</td>
          <td>{candidate.ontology_term} ({candidate.target_ontology_type})</td>
          <td>{candidate.eligible ? 'Reviewable' : 'Invalid'}{[...(candidate.validation_errors || []), ...(candidate.validation_warnings || [])].map((text, index) => <div key={index}>{text}</div>)}</td>
          <td>{Math.round((candidate.confidence || 0) * 100)}%</td>
        </tr>)}</tbody>
      </table></div>
      {!preview.candidates.length && <p>No candidates found. Check the imported data and ontology before creating another preview.</p>}
      <label><input type="checkbox" aria-label="Confirm reviewed mappings" checked={confirmed} disabled={busy || !selected.length || job?.status === 'published'} onChange={e => setConfirmed(e.target.checked)} /> I reviewed these {selected.length} mappings and approve their publication.</label><br />
      <button type="button" style={buttonStyle} disabled={!canPublish} onClick={() => invoke(async current => {
        // Freeze the selection immediately; response loss must not allow editing.
        setJob({ job_id: preview.publication_job_id, status: 'publishing', approved_ids: selected });
        try {
          const result = await api.publish(preview.job_id, selected, { approved_by: actor, approval_token: getCredentialProfile('AGENTIC_APPROVAL_TOKEN') });
          if (current()) { setJob(result.data); setConfirmed(false); }
        } finally { /* Shared credentials remain managed in Admin. */ }
      })}>{busy ? 'Working…' : job ? 'Retry same publication' : 'Publish approved mappings'}</button>
      <button type="button" style={buttonStyle} disabled={busy || !preview.publication_job_id} onClick={() => invoke(refresh)}>Refresh publication status</button>
      <button type="button" style={buttonStyle} disabled={busy} onClick={() => invoke(async current => {
        const result = await api.artifact(job?.status === 'published' ? job.job_id : preview.job_id, getCredentialProfile('GRAPH_READ_TOKEN'));
        if (!current()) return;
        const url = URL.createObjectURL(result.data); const link = document.createElement('a');
        link.href = url; link.download = 'semantic-bridge-job.json'; link.click(); URL.revokeObjectURL(url);
      })}>Download evidence</button>
      {job && <div role="status"><strong>Publication: {job.status}</strong><div>{job.job_id}</div>
        {job.receipt && <p>{job.receipt.applied_links} mappings published. Approved by {job.receipt.approved_by}.</p>}
        {job.error && <p>{job.error}</p>}
      </div>}
    </>}
  </section>;
}

function authOptions(token) {
  return token ? { headers: { Authorization: `Bearer ${token}` } } : {};
}
