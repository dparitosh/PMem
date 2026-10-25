import React from 'react';

const holdReasons = {
  decision_policy_blocked: "A configured Semantica decision rule did not pass. Expand Shared decision policy for its findings.",
  decision_policy_unavailable: "Shared decision policy could not be assessed; publication is held until the service and evidence store recover.",
  identity_requires_domain_review: 'Identity assertions need domain review. A class assignment or high similarity score does not establish that two resources are identical.',
  invalid_target_or_source: 'The source or ontology target did not pass validation.',
  not_automatically_validated: 'Semantic compatibility has not been verified for automatic publication.',
  validation_warning: 'Validation found questions that need review.',
  ambiguous_target: 'The source does not have one unambiguous first-choice target.',
  non_specific_or_alternative_match: 'This is a generic term or an alternative rather than a specific first-choice match.',
  insufficient_confidence: 'The recorded match score is missing, invalid, or below the automatic publication threshold.',
};
export const explainHoldReason = reason => holdReasons[reason] || 'An additional policy check requires review; inspect the retained evidence.';
export const matchScore = candidate => typeof candidate.confidence === 'number' && Number.isFinite(candidate.confidence)
  && candidate.confidence >= 0 && candidate.confidence <= 1 ? `${Math.round(candidate.confidence * 100)}%` : 'Not recorded';
const sourceKey = row => row.import_id && row.import_row_key
  ? JSON.stringify([row.import_id, row.import_row_key, row.source_type, row.source_term]) : null;
const targetName = row => `${row.ontology_term || 'Unnamed target'} (${row.target_ontology_type || 'type not recorded'})`;
const evidenceText = value => typeof value === 'string'
  ? (value === 'element_type' || value === 'source_element_name' ? 'The source element type contributed to this match.' : value)
  : 'Structured evidence is retained in the downloaded report.';

export default function MappingExplanation({ candidate, candidates, decisions = [] }) {
  const identity = sourceKey(candidate);
  const alternatives = identity ? candidates.filter(row => row.candidate_id !== candidate.candidate_id && sourceKey(row) === identity) : [];
  const evidence = Array.isArray(candidate.evidence) ? candidate.evidence : [];
  const validScore = matchScore(candidate) !== 'Not recorded';
  const decision = decisions.find(row => row.candidate_id === candidate.candidate_id);
  const warnings = [...(candidate.validation_errors || []), ...(candidate.validation_warnings || [])];
  const needsReview = !candidate.eligible || candidate.ambiguous || candidate.generic_match || alternatives.length > 0
    || !identity || !validScore || candidate.confidence < .9 || candidate.rank !== 1 || !evidence.length
    || warnings.length > 0 || candidate.validation_status !== 'auto_approved' || decision?.decision === 'hold';
  const iri = candidate.target_ontology_iri || candidate.ontology_iri;
  return <article aria-label={`Mapping explanation ${candidate.candidate_id}`} style={{border:'1px solid var(--ui-border,#d5dfe9)',borderRadius:6,padding:12,margin:'8px 0',background:'var(--ui-surface,#fff)'}}>
    <strong>{candidate.source_label || candidate.source_term || candidate.import_row_key || 'Unnamed source'} → {targetName(candidate)}</strong>
    <p><strong>{decision?.decision === 'publish' ? 'Policy-approved' : needsReview ? 'Review needed' : 'Policy validation recorded'}</strong> · Recorded match score: {matchScore(candidate)}. This score is not a probability of semantic correctness.</p>
    <dl>
      <dt><strong>What is being mapped</strong></dt><dd>Source type: {candidate.source_type || 'not recorded'}; row: {candidate.import_row_key || 'not recorded'}. {iri && <span>Target IRI: {iri}.</span>}</dd>
      <dt><strong>Why this target was suggested</strong></dt><dd>{evidence.length ? evidence.map(evidenceText).join(' ') : 'No supporting rationale was recorded. Do not infer a semantic match from the score alone.'}</dd>
      <dt><strong>Other possibilities</strong></dt><dd>{alternatives.length ? <ul>{alternatives.map(row => <li key={row.candidate_id}>{targetName(row)} · {row.target_ontology_iri || row.ontology_iri || row.ontology_class_element_id || row.candidate_id} · match score {matchScore(row)}</li>)}</ul> : !identity ? 'Alternative matching cannot be established because source identity is missing.' : 'No alternatives were retained in this preview batch. This does not establish a unique match across the ontology.'}</dd>
      <dt><strong>What is uncertain</strong></dt><dd>{warnings.length ? <ul>{warnings.map((text,index) => <li key={index}>{text}</li>)}</ul> : 'No validation warnings were recorded. Review the supporting evidence before approval.'}
        {decision?.reasons?.length > 0 && <ul>{decision.reasons.map(reason => <li key={reason}>{explainHoldReason(reason)}</li>)}</ul>}</dd>
      <dt><strong>What approval would do</strong></dt><dd>{candidate.eligible ? `Publication would create or update a SEMANTICALLY_MAPPED_TO link from this imported row to ${candidate.ontology_term || 'the selected target'}.${candidate.target_ontology_type === 'Class' ? ' A class target also receives an INSTANCE_OF link.' : ''} Approval still requires the selected mappings and publication confirmation.` : 'This candidate is ineligible; publication is blocked until the underlying validation problem is corrected.'}</dd>
      <dt><strong>Your next action</strong></dt><dd>{!candidate.eligible ? 'Correct the source or target validation errors and generate a new preview.' : needsReview ? 'Check the source context and target definition. For a relationship, establish the domain and range classes; compare the alternatives. Leave this unselected if you cannot establish the meaning.' : 'Verify the source context and target definition, then select only the mappings you accept and confirm publication.'}</dd>
    </dl>
    <details><summary>Technical trace</summary><p>Candidate: {candidate.candidate_id}. Evidence is from the retained preview; this explanation does not add model reasoning or validation.</p></details>
  </article>;
}
