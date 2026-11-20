import React from 'react';

export default function SemanticSupport({ report }) {
  if (!report) return null;
  if (Array.isArray(report)) return <>{report.map((item, index) => <SemanticSupport key={item.ontology_id || index} report={item} />)}</>;
  return <section aria-label="Semantic decision evidence" className="depo-alert">
    <strong>Model check: {({not_checked:'Not run yet',consistent:'No conflicts found',inconsistent:'Conflicts found',unsupported:'Unsupported logical model',unknown:'Unverified',supports_review:'Ready for review'})[report.status] || 'Status unknown'}</strong>
    <p>{report.business_summary || 'No current reasoning assessment is available.'}</p>
    {report.next_action && <p>Next step: {report.next_action}.</p>}
    <small>This check helps you review the model. It does not confirm that your data is correct, that two parts are interchangeable, or that anything is approved.</small>
    {(report.unparsed_statement_count > 0 || report.profile_violation_count > 0) && <details><summary>Validation findings</summary>
      {report.profile_complete_for_input === false && <p>Profile findings cover parsed statements only.</p>}
      {report.unparsed_statement_count > 0 && <><p>{report.unparsed_statement_count} unparsed statements</p><ul>{(report.unparsed_statements || []).slice(0,20).map((value,index)=><li key={index} style={{overflowWrap:'anywhere'}}>{value}</li>)}</ul></>}
      {report.profile_violation_count > 0 && <><p>{report.profile_violation_count} profile findings</p><ul>{Object.entries(report.profile_violation_counts || {}).map(([name,count])=><li key={name}>{name}: {count}</li>)}</ul><ul>{(report.profile_violation_samples || []).slice(0,20).map((value,index)=><li key={index} style={{overflowWrap:'anywhere'}}>{value}</li>)}</ul></>}
    </details>}
    {report.evidence_id && <details><summary>Evidence revision</summary><dl><dt>Ontology</dt><dd>{report.ontology_id || 'Proposed union'}</dd><dt>Checked</dt><dd>{report.checked_at || 'Not recorded'}</dd><dt>Source digest</dt><dd style={{overflowWrap:'anywhere'}}>{report.artifact_sha256}</dd></dl></details>}
  </section>;
}
