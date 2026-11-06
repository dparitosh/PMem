import React, { useEffect, useMemo, useState } from 'react';
import MappingExplanation, { matchScore } from './MappingExplanation';
import './MappingReviewTable.css';

const reasonLabels = {
  ambiguous_target: 'Multiple matching targets',
  identity_requires_domain_review: 'Identity needs domain review',
  invalid_target_or_source: 'Source or target is invalid',
  decision_policy_blocked: 'Decision policy did not pass',
  decision_policy_unavailable: 'Decision policy unavailable',
  not_automatically_validated: 'Semantic validation incomplete',
  validation_warning: 'Validation needs review',
  non_specific_or_alternative_match: 'Generic or alternative target',
  insufficient_confidence: 'Match score below policy threshold',
};
const priority = Object.keys(reasonLabels);
function rowState(candidate, decision) {
  const reasons = decision?.reasons || [];
  const key = priority.find(reason => reasons.includes(reason));
  const issue = key ? reasonLabels[key] : candidate.validation_errors?.[0] || candidate.validation_warnings?.[0];
  if (decision?.decision === 'hold') return { status: 'Held', reason: issue || 'Policy review required' };
  if (decision?.decision === 'publish') return { status: 'Policy-approved', reason: 'Passed recorded publication policy' };
  return { status: 'Not assessed', reason: issue || (candidate.evidence?.length ? 'Awaiting Steward assessment' : 'No supporting rationale recorded') };
}

export default function MappingReviewTable({ candidates = [], decisions = [] }) {
  const [filter, setFilter] = useState('all');
  const [category, setCategory] = useState('all');
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState(null);
  const [collapsedGroups, setCollapsedGroups] = useState(new Set());
  const rows = useMemo(() => {
    const index = new Map(decisions.map(decision => [decision.candidate_id, decision]));
    return candidates.map(candidate => ({ candidate, ...rowState(candidate, index.get(candidate.candidate_id)) }));
  }, [candidates, decisions]);
  useEffect(() => { setPage(0); setExpanded(null); setCollapsedGroups(new Set()); }, [candidates, filter, category]);
  const held = rows.filter(row => row.status === 'Held').length;
  const approved = rows.filter(row => row.status === 'Policy-approved').length;
  const categoryFor = candidate => ({ Entity: 'Entity classification', Relationship: 'Relationship mapping', Attribute: 'Attribute mapping', Metadata: 'Metadata mapping' }[candidate.source_type] || 'Other mappings');
  const categories = [...new Set(rows.map(row => categoryFor(row.candidate)))];
  const filtered = rows.filter(row => (filter === 'all' || row.status === filter) && (category === 'all' || categoryFor(row.candidate) === category));
  const groups = new Map();
  filtered.forEach(row => {
    const c = row.candidate;
    // Repeated names can belong to different revisions or imports.
    const key = c.import_id && c.import_row_key ? JSON.stringify([c.import_id, c.import_row_key, c.source_type]) : c.candidate_id;
    if (!groups.has(key)) groups.set(key, { key, category: categoryFor(c), candidate: c, rows: [] });
    groups.get(key).rows.push(row);
  });
  const grouped = [...groups.values()].sort((a, b) => a.category.localeCompare(b.category));
  const pageCount = Math.max(1, Math.ceil(grouped.length / 25));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = grouped.slice(currentPage * 25, (currentPage + 1) * 25);
  return <section className="mapping-review" aria-label="Mapping guidance">
    <header className="mapping-review__summary"><h4>Mapping review</h4>
    <p><strong>{rows.length} proposals</strong> · {approved} policy-approved · {held} held · {rows.length - held - approved} not assessed</p>
    </header>
    <div className="mapping-review__toolbar">
    <label>Show mappings <select value={filter} onChange={event => setFilter(event.target.value)}>
      <option value="all">All proposals</option><option value="Held">Held</option><option value="Policy-approved">Policy-approved</option><option value="Not assessed">Not assessed</option>
    </select></label>
    <label>Mapping category <select value={category} onChange={event => setCategory(event.target.value)}>
      <option value="all">All categories</option>{categories.map(value => <option key={value} value={value}>{value} ({rows.filter(row => categoryFor(row.candidate) === value).length})</option>)}
    </select></label>
    {grouped.length > 0 && <div className="mapping-review__group-actions"><button type="button" onClick={() => { setCollapsedGroups(new Set(grouped.map(group => group.key))); setExpanded(null); }}>Collapse all sources</button><button type="button" onClick={() => setCollapsedGroups(new Set())}>Expand all sources</button></div>}
    </div>
    <p className="mapping-review__scope">{grouped.length} source records · alternatives grouped by source · scores indicate similarity, not semantic correctness</p>
    <div className="mapping-review__scroll" role="region" aria-label="Mapping results" tabIndex={0}><table>
      <caption>Proposed source-to-ontology mappings</caption>
      <thead><tr><th scope="col">Proposed target</th><th scope="col">Match score</th><th scope="col">Decision</th><th scope="col">Main finding</th><th scope="col">Evidence</th></tr></thead>
      {visible.map((group, index) => <tbody key={group.key} aria-label={`Source ${group.candidate.import_row_key || group.candidate.candidate_id}`}>
        {(index === 0 || visible[index - 1].category !== group.category) && <tr className="mapping-review__category"><th colSpan={5} scope="colgroup">{group.category}</th></tr>}
        <tr className="mapping-review__source"><th colSpan={5} scope="rowgroup"><button className="mapping-review__source-toggle" type="button" aria-expanded={!collapsedGroups.has(group.key)} onClick={() => setCollapsedGroups(current => { const next = new Set(current); if (next.has(group.key)) next.delete(group.key); else next.add(group.key); return next; })}><span aria-hidden="true">{collapsedGroups.has(group.key) ? '▸' : '▾'} </span>{group.candidate.source_label || group.candidate.source_term || group.candidate.import_row_key || 'Unnamed source'}<span className="mapping-review__source-count">{group.rows.length} target{group.rows.length === 1 ? '' : 's'}</span></button><small>{group.candidate.source_type || 'Type not recorded'} · Row {group.candidate.import_row_key || 'not recorded'} · {group.rows.filter(row => row.status === 'Held').length} held · {group.rows.filter(row => row.status === 'Policy-approved').length} policy-approved · {group.rows.filter(row => row.status === 'Not assessed').length} not assessed</small></th></tr>
        {!collapsedGroups.has(group.key) && group.rows.map(({ candidate, status, reason }) => <React.Fragment key={candidate.candidate_id}>
        <tr><td><strong>{candidate.ontology_term || 'Unnamed target'}</strong><small>{candidate.target_ontology_type || 'Type not recorded'}</small><small className="mapping-review__iri" title={candidate.target_ontology_iri || candidate.ontology_iri || undefined}>{candidate.target_ontology_iri || candidate.ontology_iri || 'IRI not recorded'}</small></td>
          <td>{matchScore(candidate)}</td><td><span className={`mapping-review__status ${status === 'Held' ? 'mapping-review__status--held' : ''}`}>{status}</span></td><td>{reason}</td>
          <td><button type="button" aria-expanded={expanded === candidate.candidate_id} aria-label={`Evidence for ${candidate.source_term || candidate.import_row_key || 'source'} to ${candidate.ontology_term || 'target'} (${candidate.candidate_id})`} onClick={() => setExpanded(expanded === candidate.candidate_id ? null : candidate.candidate_id)}>{expanded === candidate.candidate_id ? 'Hide' : 'View'}</button></td></tr>
        {expanded === candidate.candidate_id && <tr><td colSpan={5}><MappingExplanation candidate={candidate} candidates={candidates} decisions={decisions} /></td></tr>}
      </React.Fragment>)}</tbody>)}
    </table></div>
    {!filtered.length && <p>No mappings in this view.</p>}
    {pageCount > 1 && <nav aria-label="Mapping result pages"><button type="button" disabled={!currentPage} onClick={() => { setPage(currentPage - 1); setExpanded(null); }}>Previous</button><span>Page {currentPage + 1} of {pageCount} · {grouped.length} source records · {filtered.length} proposals</span><button type="button" disabled={currentPage + 1 >= pageCount} onClick={() => { setPage(currentPage + 1); setExpanded(null); }}>Next</button></nav>}
    <p className="mapping-review__note">Review held mappings using View. Manual selection is available under Advanced; unresolved mappings remain unpublished.</p>
  </section>;
}
