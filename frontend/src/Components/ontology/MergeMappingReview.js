import React, { useEffect, useMemo, useState } from 'react';
import { API_METHODS } from '../../services/apiClient';
import { dictionaryPayload } from '../../services/ontologyPayload';
import { apiErrorMessage } from '../../utils/apiErrorMessage';
import './MergeMappingReview.css';

function Term({ label, iri }) {
  return <div className="merge-term"><strong>{label || iri || 'Not selected'}</strong>{iri && <span title={iri}>{iri}</span>}</div>;
}

export function dictionaryTerms(body) {
  const dictionary = dictionaryPayload(body);
  return [['entities', 'Class'], ['relationships', 'Object property'], ['properties', 'Datatype property']].flatMap(([key, kind]) =>
    Object.entries(dictionary[key] || {}).map(([label, value]) => ({
      label, kind, iri: value.iri || value.uri || value.term_id || '', definition: value.definition || value.description || '',
    })));
}

function Inventory({ id, label, side }) {
  const [state, setState] = useState({ rows: [], loading: false, error: '' });
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setQuery(''); setPage(0);
    setState({ rows: [], loading: Boolean(id), error: '' });
    if (id) API_METHODS.ontology.getDataDictionary(id, { signal: controller.signal, timeout: 30000 })
      .then(response => { if (active) setState({ rows: dictionaryTerms(response.data), loading: false, error: '' }); })
      .catch(error => { if (active) setState({ rows: [], loading: false, error: apiErrorMessage(error, 'Terms could not be loaded.') }); });
    return () => { active = false; controller.abort(); };
  }, [id, retry]);
  const rows = useMemo(() => state.rows.filter(row => `${row.label} ${row.kind} ${row.iri}`.toLowerCase().includes(query.toLowerCase())), [state.rows, query]);
  return <section className="merge-inventory" aria-label={`${side} term inventory`}>
    <div className="merge-section-heading"><div><span className="merge-eyebrow">{side}</span><h4>{label || 'Choose an ontology'}</h4></div><span className="merge-badge">{state.loading ? 'Loading' : state.error ? 'Unavailable' : `${state.rows.length.toLocaleString()} terms`}</span></div>
    <input aria-label={`Search ${side.toLowerCase()} terms`} placeholder="Search terms, types or identifiers" value={query} onChange={event => { setQuery(event.target.value); setPage(0); }} />
    {state.loading ? <p role="status">Loading ontology terms…</p> : state.error ? <div role="alert" className="merge-notice error">{state.error}<button type="button" onClick={() => setRetry(value => value + 1)}>Retry term loading</button></div> : <>
      <div className="merge-table-scroll"><table><caption className="merge-sr-only">{side} ontology vocabulary</caption><thead><tr><th>Ontology term</th><th>Type</th></tr></thead><tbody>{rows.slice(page * 20, (page + 1) * 20).map((row, index) => <tr key={`${row.iri}:${row.label}:${index}`}><td><Term label={row.label} iri={row.iri} />{row.definition && <details><summary>Definition</summary><p>{row.definition}</p></details>}</td><td>{row.kind}</td></tr>)}</tbody></table>{!rows.length && <p className="merge-empty">{id ? 'No matching terms returned.' : 'Select an ontology to browse its vocabulary.'}</p>}</div>
      <div className="merge-pagination"><span>{rows.length ? `${page * 20 + 1}–${Math.min((page + 1) * 20, rows.length)} of ${rows.length}` : '0 terms'}</span><button type="button" disabled={!page} onClick={() => setPage(value => value - 1)}>Previous</button><button type="button" disabled={(page + 1) * 20 >= rows.length} onClick={() => setPage(value => value + 1)}>Next</button></div>
    </>}
  </section>;
}

export default function MergeMappingReview({ sourceId, targetId, sourceLabel, targetLabel, suggestions = [], sourceIri, targetIri, onSelect, preview, busy, error }) {
  const [query, setQuery] = useState('');
  const [onlySelected, setOnlySelected] = useState(false);
  const [minimumScore, setMinimumScore] = useState(0);
  const [page, setPage] = useState(0);
  useEffect(() => { setQuery(''); setOnlySelected(false); setMinimumScore(0); setPage(0); }, [sourceId, targetId]);
  const selected = Boolean(sourceIri && targetIri);
  const rows = suggestions.filter(row => (minimumScore === 0 || (Number.isFinite(row.confidence_score) && row.confidence_score * 100 >= minimumScore)) && (!onlySelected || (row.source_iri === sourceIri && row.target_iri === targetIri)) && `${row.source_label} ${row.target_label} ${row.kind} ${row.reason} ${row.source_iri} ${row.target_iri}`.toLowerCase().includes(query.toLowerCase()));
  const conflicts = preview?.conflicts || [];
  return <div className="merge-review-workspace">
    <header className="merge-review-header"><div><span className="merge-eyebrow">Semantic Bridge / Mapping review</span><h3>Compare. Review. Merge.</h3><p>Inspect both vocabularies and the agent’s proposed source → target matches before publishing a merged ontology.</p></div><span className="merge-badge">{busy ? 'Agent processing' : error ? 'Preview failed' : preview ? 'Preview retained' : 'Awaiting agent preview'}</span></header>
    <div className="merge-metrics" aria-label="Merge review summary"><div><span>Agent suggestions</span><strong>{preview ? suggestions.length.toLocaleString() : '—'}</strong></div><div><span>Selected consolidation</span><strong>{selected ? '1 pair' : 'None'}</strong></div><div><span>Unresolved conflicts</span><strong>{preview ? conflicts.length : '—'}</strong></div><div><span>Merged statements</span><strong>{preview?.triple_count == null ? '—' : preview.triple_count.toLocaleString()}</strong></div></div>
    {error && <div className="merge-notice error" role="alert"><strong>Agent preview did not complete</strong><p>{error}</p><p>No mapping approval is available. Term browsing remains available below.</p></div>}
    <details className="merge-browser" open><summary>Browse source and target vocabularies</summary><div className="merge-comparison"><Inventory id={sourceId} label={sourceLabel} side="Source" /><Inventory id={targetId} label={targetLabel} side="Target" /></div></details>
    <section className="merge-proposals" aria-label="Agent mapping proposals"><div className="merge-section-heading"><div><span className="merge-eyebrow">Agent proposals</span><h4>Source → target mapping review</h4></div><span className="merge-badge">{selected ? 'Selection requires a fresh preview' : 'Preserve separate identities'}</span></div>
      <p>Proposals compare label tokens, character trigrams, definitions and property context for terms of the same declared kind. Scores are heuristic similarity, not calibrated probabilities or proof of equivalence. Ambiguous alternatives require explicit review. Select a pair only when the two entities represent the same concept. Approval consolidates its source identity into the target identity. Other identities are preserved.</p>
      {preview?.matching_report && <p role="status">Scoring policy: {preview.matching_report.policy}. Proposal threshold: {Math.round(preview.matching_report.minimum_score * 100)}%. {preview.matching_report.comparisons} candidate comparisons. {preview.matching_report.truncated ? "Search or output was limited; these proposals are incomplete." : "Candidate search completed within configured limits."}</p>}
      <div className="merge-toolbar"><label>Minimum similarity % <input aria-label="Minimum mapping similarity" type="number" min="0" max="100" value={minimumScore} onChange={event => {setMinimumScore(Math.min(100,Math.max(0,Number(event.target.value) || 0)));setPage(0);}} /></label><input aria-label="Search proposed mappings" placeholder="Search source, target or rationale" value={query} onChange={event => { setQuery(event.target.value); setPage(0); }} /><label><input type="checkbox" checked={onlySelected} onChange={event => { setOnlySelected(event.target.checked); setPage(0); }} /> Selected only</label><button type="button" disabled={!selected || busy} onClick={() => onSelect(null)}>Clear selection</button></div>
      <div className="merge-table-scroll"><table><caption className="merge-sr-only">Agent proposed source to target consolidations</caption><thead><tr><th>Source term</th><th>Target term</th><th>Type & rationale</th><th>Similarity evidence</th><th>Review decision</th></tr></thead><tbody>{rows.slice(page * 20, (page + 1) * 20).map(row => { const chosen = row.source_iri === sourceIri && row.target_iri === targetIri; return <tr key={`${row.source_iri}:${row.target_iri}`} className={chosen ? 'selected' : ''}><td><Term label={row.source_label} iri={row.source_iri} /></td><td><Term label={row.target_label} iri={row.target_iri} /></td><td><span className="merge-badge">{row.kind}</span><p>{row.reason || 'No rationale supplied by the agent.'}</p>{(row.source_evidence || row.target_evidence) && <details><summary>Compare definitions, domain and range</summary><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify({source:row.source_evidence,target:row.target_evidence},null,2)}</pre></details>}</td><td><strong>{Number.isFinite(row.confidence_score) ? `${Math.round(row.confidence_score * 100)}% similarity` : "Score unavailable"}</strong>{row.ambiguous && <p role="status">Ambiguous alternative</p>}{row.score_components && <dl>{Object.entries(row.score_components).map(([signal,value]) => <React.Fragment key={signal}><dt>{signal.replaceAll("_", " ")}</dt><dd>{Math.round(value * 100)}%</dd></React.Fragment>)}</dl>}</td><td><button type="button" aria-pressed={chosen} disabled={busy} onClick={() => onSelect(chosen ? null : row)}>{chosen ? 'Selected — remove' : 'Select for consolidation'}</button></td></tr>; })}</tbody></table>{!rows.length && <div className="merge-empty"><strong>{!preview && !suggestions.length ? 'Generate an agent preview to see proposed mappings' : 'No proposed mappings match this view'}</strong><p>{!preview ? 'The source and target inventories can be inspected before running the agent.' : 'No inferred equivalence is added automatically. A merge can retain both vocabularies without consolidation.'}</p></div>}</div>
      <div className="merge-pagination"><span>{rows.length} matching proposals · 20 per page</span><button type="button" disabled={!page} onClick={() => setPage(value => value - 1)}>Previous</button><button type="button" disabled={(page + 1) * 20 >= rows.length} onClick={() => setPage(value => value + 1)}>Next</button></div>
      {selected && <div className="merge-notice"><strong>Selected identity change</strong><Term label="Source" iri={sourceIri} /><span>will be consolidated into</span><Term label="Target" iri={targetIri} /><p>Generate a new review plan to validate this selection before approval.</p></div>}
      {conflicts.length > 0 && <div className="merge-notice error"><strong>{conflicts.length} conflicts block approval</strong><details><summary>Inspect conflict evidence</summary><pre>{JSON.stringify(conflicts, null, 2)}</pre></details></div>}
      {preview?.changes && <div className="merge-notice"><strong>Impact against the target ontology</strong><p>{preview.changes.added} statements added · {preview.changes.removed} removed · {preview.changes.unchanged} unchanged · {preview.changes.modified_entity_count} identities consolidated.</p></div>}
    </section>
  </div>;
}
