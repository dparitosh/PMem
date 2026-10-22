import React from 'react';

export default function DecisionPolicyAssessment({ report }) {
  if (!report) return <p role="status">Shared decision policy evidence is unavailable. Refresh after the updated services are running.</p>;
  const labels = {
    not_configured: 'No shared decision policy is configured for this operation. Existing validation and approval rules still apply.',
    not_applicable: 'There are no candidates to assess.',
    passed: 'Configured decision policies passed. Domain review and publication approval still apply.',
    blocked: 'Decision policy holds this proposal. Review the findings before proceeding.',
    unavailable: 'Decision policy could not be assessed. Publication is held; check the policy service and retry.',
  };
  return <section aria-label="Shared decision policy" role="status">
    <strong>Decision policy</strong><p>{labels[report.status] || 'Unrecognized policy result; refresh and reassess.'}</p>
    {report.checks?.length > 0 && <details><summary>Policy findings and evidence</summary>
      <ul>{report.checks.slice(0, 200).map((check, index) => <li key={index}>{check.subject && <span>{check.subject} · </span>}{check.policy_id}: {check.compliant ? 'Passed' : 'Held'}
        {[...(check.violations || []), ...(check.warnings || [])].map((text, i) => <p key={i}>{text}</p>)}</li>)}</ul>
      {(report.checks_truncated || report.checks.length > 200) && <p>Showing the first 200 checks; the retained assessment includes all checks.</p>}
      <p>Assessment: {report.assessment_id}. Policy snapshot: {report.policy_digest}.</p>
    </details>}
  </section>;
}
