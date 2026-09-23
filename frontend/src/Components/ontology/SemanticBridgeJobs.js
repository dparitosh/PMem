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
  const [readToken, setReadToken] = useState('');
  const [actor, setActor] = useState('');
  const [approvalToken, setApprovalToken] = useState('');
  const [resumeId, setResumeId] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [agentReport, setAgentReport] = useState(null);
  const generation = useRef(0);
  useEffect(() => {
    generation.current += 1;
    setPreview(null); setJob(null); setSelected([]); setMessage(''); setBusy(false); setAgentReport(null);
    setConfirmed(false); setApprovalToken('');
    try { setResumeId(sessionStorage.getItem(`bridge-preview:${ontologyId}:${importTaskId}`) || ''); } catch { setResumeId(''); }
    return () => { generation.current += 1; };
  }, [ontologyId, importTaskId]);

  const invoke = async (operation) => {
    const current = generation.current;
    setBusy(true); setMessage('');
    try { await operation(() => current === generation.current); }
    catch (error) { if (current === generation.current) setMessage(errorMessage(error)); }
    finally { if (current === generation.current) setBusy(false); }
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
    try { response = await api.status(preview.publication_job_id, readToken); }
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
  const canPublish = preview && selected.length > 0 && confirmed && !busy && !['published', 'stale'].includes(job?.status);
  const buttonStyle = { padding: '8px 12px', marginRight: 8, marginTop: 8 };
  return <section aria-label="Governed Semantic Bridge jobs" style={{ background: '#fff', padding: 16, border: '1px solid #ccd5df', borderRadius: 8, marginTop: 16 }}>
    <h3>Preview → review → publish</h3>
    <p>Create a saved preview, select valid mappings, then approve publication. Nothing is selected automatically.</p>
    <details><summary>Bootstrap authentication (use gateway identity in production)</summary>
      <p>Credentials are held only in this component’s memory. Do not use these fields on an untrusted connection.</p>
      <label>Read token <input aria-label="Read token" type="password" autoComplete="off" value={readToken} onChange={e => setReadToken(e.target.value)} /></label>{' '}
      <label>Approver <input aria-label="Approver" value={actor} onChange={e => setActor(e.target.value)} /></label>{' '}
      <label>Approval token <input aria-label="Approval token" type="password" autoComplete="off" value={approvalToken} onChange={e => setApprovalToken(e.target.value)} /></label>
    </details>
    <button style={buttonStyle} disabled={busy || !ontologyId || !importTaskId} onClick={() => invoke(async current => {
      const result = await api.preview(ontologyId, importTaskId, readToken);
      if (current()) adoptPreview(result.data);
    })}>Create preview</button>
    <button style={buttonStyle} disabled={busy || !ontologyId || !importTaskId || !agenticAPI.isConfigured()} onClick={() => invoke(async current => {
      const result = await agenticAPI.orchestrateOntology({ workflow_id: 'ontology_review', ontology_id: ontologyId, import_task_id: importTaskId }, authOptions(readToken));
      if (current()) setAgentReport(result.data);
    })}>Run ontology agent review</button>
    {!agenticAPI.isConfigured() && <small>Enable the Agentic service to run ontology intake and review.</small>}
    {agentReport && <div role="status" style={{ marginTop: 8, padding: 8, background: '#eef7fb', border: '1px solid #c5dce6' }}>
      <strong>Ontology agent review:</strong> {agentReport.steps?.length || 0} steps completed; publication requires human approval.
      {agentReport.steps?.[1]?.result?.issues?.length ? ` ${agentReport.steps[1].result.issues.length} structural issue(s) require review.` : ' No structural issues reported.'}
    </div>}
    <label>Saved preview ID <input aria-label="Saved preview ID" value={resumeId} onChange={e => setResumeId(e.target.value)} /></label>
    <button style={buttonStyle} disabled={busy || !resumeId || !ontologyId || !importTaskId} onClick={() => invoke(async current => {
      const result = await api.status(resumeId.trim(), readToken);
      if (!current()) return;
      adoptPreview(result.data);
      // Keep approval disabled until publication recovery succeeds or returns 404.
      setJob({ job_id: result.data.publication_job_id, status: 'unknown', approved_ids: [] });
      try {
        const publication = await api.status(result.data.publication_job_id, readToken);
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
      <button style={buttonStyle} disabled={!canPublish} onClick={() => invoke(async current => {
        // Freeze the selection immediately; response loss must not allow editing.
        setJob({ job_id: preview.publication_job_id, status: 'publishing', approved_ids: selected });
        try {
          const result = await api.publish(preview.job_id, selected, { approved_by: actor, approval_token: approvalToken });
          if (current()) { setJob(result.data); setConfirmed(false); }
        } finally { if (current()) setApprovalToken(''); }
      })}>{busy ? 'Working…' : job ? 'Retry same publication' : 'Publish approved mappings'}</button>
      <button style={buttonStyle} disabled={busy} onClick={() => invoke(refresh)}>Refresh publication status</button>
      <button style={buttonStyle} disabled={busy} onClick={() => invoke(async current => {
        const result = await api.artifact(job?.status === 'published' ? job.job_id : preview.job_id, readToken);
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
