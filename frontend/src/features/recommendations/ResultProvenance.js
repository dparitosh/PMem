import React from 'react';
import './ResultProvenance.css';

// Policy statuses come from the backend decision-policy assessment.
const POLICY_LABELS = {
  passed: 'Policy checks passed',
  blocked: 'Policy checks blocked this result',
  not_configured: 'No policy configured for this analysis',
  not_applicable: 'Policy not applicable to this analysis',
  unavailable: 'Policy check unavailable',
};

export function ResultProvenance({ mode, policy, observationId }) {
  const source = mode === 'agent'
    ? `Agent investigation${observationId ? `, cites observation ${observationId}` : ''}`
    : 'Direct graph read';
  const policyLabel = POLICY_LABELS[policy?.status] || 'Policy status not reported';
  return (
    <dl className="recommendation-provenance" aria-label="Result provenance">
      <div><dt>Source</dt><dd>{source}</dd></div>
      <div><dt>Policy</dt><dd>{policyLabel}</dd></div>
      <div><dt>Approval</dt><dd>Not granted. Evidence for review only.</dd></div>
    </dl>
  );
}
