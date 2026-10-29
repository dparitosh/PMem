import React from 'react';

export default function SemanticSupport({ report }) {
  if (!report) return null;
  if (Array.isArray(report)) return <>{report.map((item, index) => <SemanticSupport key={item.ontology_id || index} report={item} />)}</>;
  return <section aria-label="Semantic decision evidence" className="depo-alert">
    <strong>Model evidence: {report.status || 'unknown'}</strong>
    <p>{report.business_summary || 'No current reasoning assessment is available.'}</p>
    {report.next_action && <p>Next action: {report.next_action}.</p>}
    <small>Model consistency supports review. It does not establish instance conformance, part interchangeability or approval.</small>
    {report.evidence_id && <details><summary>Evidence revision</summary><dl><dt>Ontology</dt><dd>{report.ontology_id || 'Proposed union'}</dd><dt>Checked</dt><dd>{report.checked_at || 'Not recorded'}</dd><dt>Source digest</dt><dd style={{overflowWrap:'anywhere'}}>{report.artifact_sha256}</dd></dl></details>}
  </section>;
}
