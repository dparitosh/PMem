import DecisionPolicyAssessment from '../DecisionPolicyAssessment';
import React, { useEffect, useState } from 'react';
import { ontologyMergeAgent } from '../../services/ontologyMergeAgent';
import { apiErrorMessage } from '../../utils/apiErrorMessage';

export default function MergeStewardReview({ reviewKey, previewId, enabled, reviewer, onReview }) {
  const [state, setState] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    const update = value => { if (active) { setState(value); onReview(value); } };
    update(null);
    if (enabled && previewId && reviewer.trim()) {
      update({key: reviewKey, status: 'running'});
      ontologyMergeAgent.evaluate(previewId, reviewer).then(response => update({key: reviewKey, status: 'completed',
        runId: response.runId, result: response.result})).catch(error => update({key: reviewKey, status: 'failed',
        error: apiErrorMessage(error, 'Steward evaluation failed. Approval remains blocked.')}));
    }
    return () => { active = false; };
  }, [reviewKey, previewId, enabled, reviewer, onReview, retry]);
  const report = state?.key === reviewKey ? state.result?.governance : null;
  return <section className="merge-workflow" aria-label="Ontology Steward assessment">
    <h4>Ontology Steward assessment</h4>
    <p>The Governor prepares and publishes the saved plan. The existing Steward checks its governance evidence before publication. Model explanations cannot override these checks.</p>
    {!enabled && <p>Generate and validate the current mapping plan to start the Steward assessment.</p>}
    {state?.status === 'running' && <p role="status">Steward is evaluating the retained plan; no graph changes are being made.</p>}
    {state?.status === 'failed' && <div role="alert"><p>{state.error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Retry Steward assessment</button></div>}
    {report && <>
      <DecisionPolicyAssessment report={report.decision_policy} />
      <p role="status"><strong>{report.overall_verdict === 'APPROVED' && !report.decision_policy?.blocking ? 'Steward checks passed — human review and publication approval remain required' : report.overall_verdict === 'PENDING_VALIDATION' ? 'Validation evidence is incomplete' : 'Publication held — review the findings below'}</strong></p>
      <p>Profile: {report.profile === 'enterprise_curated' ? 'Curated enterprise' : report.profile === 'imported_standard' ? 'Imported standard' : report.profile}. Suggested version change: {report.recommended_version_bump}. Findings: {report.metrics?.findings ?? 'unavailable'}. Identifiers held for review: {report.metrics?.quarantined_subjects ?? 'unavailable'}.</p>
      <p><strong>Next action:</strong> {report.overall_verdict === 'APPROVED' && !report.decision_policy?.blocking ? 'Review the mappings and changes, then use Approve merge and publish when satisfied.' : 'Expand the findings, follow the recommended actions and generate a revised plan. Approval is blocked.'}</p>
      <p>No automatic renaming or predicate changes were applied. {report.coverage?.foundation_alignment === 'not_configured' && 'Foundation alignment is not configured. '}Full OWL-DL consistency and domain equivalence are not established.</p>
      {report.violations_and_remediations.length > 0 && <details><summary>Review governance findings and proposed actions</summary><div className="merge-table-scroll"><table><thead><tr><th>Identifier</th><th>Rule / severity</th><th>Finding</th><th>What you should do</th></tr></thead><tbody>{report.violations_and_remediations.map((finding, index) => <tr key={index}><td style={{overflowWrap:'anywhere'}}>{finding.subject_uri}</td><td>{finding.issue_category.replaceAll('_',' ').toLowerCase()} / {finding.severity === 'BLOCKER' ? 'Blocks publication' : 'Review advice'}</td><td>{finding.diagnosis}</td><td>{finding.recommended_action || 'Review the cited evidence with the domain steward.'}</td></tr>)}</tbody></table></div></details>}
      {report.findings_truncated && <p role="status">Only the first 200 findings are displayed. Counts and the verdict include all findings.</p>}
      <details><summary>Audit identity, validation coverage and provenance</summary><p>Steward run: {state.runId}. Audit: {report.audit_id}.</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({policy_version:report.policy_version,policy_sha256:report.policy_sha256,artifact_sha256:report.artifact_sha256,sources:report.sources,coverage:report.coverage},null,2)}</pre><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{report.provenance_turtle}</pre></details>
    </>}
  </section>;
}
