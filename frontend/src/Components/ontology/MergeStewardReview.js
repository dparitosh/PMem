import DecisionPolicyAssessment from '../DecisionPolicyAssessment';
import React, { useEffect, useRef, useState } from 'react';
import { ontologyMergeAgent } from '../../services/ontologyMergeAgent';
import { apiErrorMessage } from '../../utils/apiErrorMessage';

export default function MergeStewardReview({ reviewKey, previewId, enabled, reviewer, onReview, preview, dirty = false }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const identity = JSON.stringify([reviewKey, previewId, enabled, reviewer]);
  const inFlight = useRef(false), currentKey = useRef(identity), mounted = useRef(true);
  currentKey.current = identity;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    setState(null); onReview(null);
  }, [reviewKey, previewId, enabled, reviewer, onReview]);
  const assess = async () => {
    if (inFlight.current || !enabled || !previewId || !reviewer.trim()) return;
    inFlight.current = true; setBusy(true);
    const key = reviewKey;
    const update = value => { if (mounted.current && currentKey.current === identity) { setState(value); onReview(value); } };
    update({key, status: 'running'});
    try {
      const response = await ontologyMergeAgent.evaluate(previewId, reviewer.trim());
      update({key, status: 'completed', runId: response.runId, result: response.result});
    } catch (error) {
      update({key, status: 'failed', error: apiErrorMessage(error, 'Steward evaluation failed. Approval remains blocked.')});
    } finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };
  const report = state?.key === reviewKey ? state?.result?.governance : null;
  const pending = preview?.background_validation && ['queued','preparing','validating'].includes(preview.job_status);
  const reason = preview?.owl_dl_evidence?.reason || preview?.semantic_support?.reason;
  const unavailable = !previewId ? 'Generate a mapping plan.' : dirty ? 'Selected mappings need validation.' : pending ? 'Validation running.' : preview?.job_status === 'failed' ? 'Validation failed. Open the report.' : reason === 'unparsed_rdf_statements' ? 'Assessment blocked: logical validation cannot process all ontology statements.' : preview?.publish_recommended === false ? 'Assessment blocked by validation findings. Open the report.' : 'Validation evidence is unverified. Open the report.';
  return <section className="merge-workflow" aria-label="Ontology Steward assessment">
    <h4>Ontology Steward assessment</h4>
    {!enabled && <p role="status">{unavailable}</p>}
    {enabled && <button type="button" disabled={busy || !previewId || !reviewer.trim()} onClick={assess}>{busy ? 'Steward assessment in progress' : 'Run Steward assessment'}</button>}
    {state?.status === 'running' && <p role="status">Steward is evaluating the retained plan; no graph changes are being made.</p>}
    {state?.status === 'failed' && <div role="alert"><p>{state.error}</p></div>}
    {report && <>
      <DecisionPolicyAssessment report={report.decision_policy} />
      <p role="status"><strong>{report.overall_verdict === 'APPROVED' && !report.decision_policy?.blocking ? 'Steward checks passed — human review and publication approval remain required' : report.overall_verdict === 'PENDING_VALIDATION' ? 'Validation evidence is incomplete' : 'Publication held — review the findings below'}</strong></p>
      <p>Profile: {report.profile === 'enterprise_curated' ? 'Curated enterprise' : report.profile === 'imported_standard' ? 'Imported standard' : report.profile}. Suggested version change: {report.recommended_version_bump}. Findings: {report.metrics?.findings ?? 'unavailable'}. Identifiers held for review: {report.metrics?.quarantined_subjects ?? 'unavailable'}.</p>
      <p><strong>Next action:</strong> {report.overall_verdict === 'APPROVED' && !report.decision_policy?.blocking ? 'Review the mappings, then request CR/CO authorization.' : 'Expand the findings, follow the recommended actions and generate a revised plan. Approval is blocked.'}</p>
      <p>No automatic renaming or predicate changes were applied. {report.coverage?.foundation_alignment === 'not_configured' && 'Foundation alignment is not configured. '}Full OWL-DL consistency and domain equivalence are not established.</p>
      {report.violations_and_remediations.length > 0 && <details><summary>Review governance findings and proposed actions</summary><div className="merge-table-scroll"><table><thead><tr><th>Identifier</th><th>Rule / severity</th><th>Finding</th><th>What you should do</th></tr></thead><tbody>{report.violations_and_remediations.map((finding, index) => <tr key={index}><td style={{overflowWrap:'anywhere'}}>{finding.subject_uri}</td><td>{finding.issue_category.replaceAll('_',' ').toLowerCase()} / {finding.severity === 'BLOCKER' ? 'Blocks publication' : 'Review advice'}</td><td>{finding.diagnosis}</td><td>{finding.recommended_action || 'Review the cited evidence with the domain steward.'}</td></tr>)}</tbody></table></div></details>}
      {report.findings_truncated && <p role="status">Only the first 200 findings are displayed. Counts and the verdict include all findings.</p>}
      <details><summary>Audit identity, validation coverage and provenance</summary><p>Steward run: {state.runId}. Audit: {report.audit_id}.</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({policy_version:report.policy_version,policy_sha256:report.policy_sha256,artifact_sha256:report.artifact_sha256,sources:report.sources,coverage:report.coverage},null,2)}</pre><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{report.provenance_turtle}</pre></details>
    </>}
  </section>;
}
