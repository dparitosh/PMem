import React, { useEffect, useState } from 'react';
import './MergeMappingReview.css';

function Term({ label, iri }) {
  return <div className="merge-term"><strong>{label || iri || 'Not selected'}</strong>{iri && <span title={iri}>{iri}</span>}</div>;
}

function similarityParts(row, report) {
  const recorded = row.score_components || {};
  const weights = report?.weights || ((row.score_policy || report?.policy) === 'lexical-context-v2' ? {label_similarity:.5,character_trigrams:.3,definitions:.1,property_context:.1} : {});
  return Object.entries(recorded).map(([name,value])=>({name,value,weight:Number.isFinite(weights[name])&&weights[name]>=0&&weights[name]<=1?weights[name]:undefined})).filter(item=>Number.isFinite(item.value)&&item.value>=0&&item.value<=1);
}
function rationale(row) {
  const parts=row.score_components;
  if (!parts) return row.reason || 'Matching rationale not recorded';
  const definitions = row.source_evidence?.definitions?.length && row.target_evidence?.definitions?.length;
  const context = ['domains','ranges','properties'].some(key=>row.source_evidence?.[key]?.length) && ['domains','ranges','properties'].some(key=>row.target_evidence?.[key]?.length);
  return `Label overlap ${Math.round((parts.label_similarity || 0)*100)}%; ${definitions ? `definition overlap ${Math.round((parts.definitions || 0)*100)}%` : 'definitions not comparable'}; ${context ? `direct context overlap ${Math.round((parts.property_context || 0)*100)}%` : 'direct context not comparable'}. Meaning unverified.`;
}

function ConceptEvidence({ title, value = {}, kind = '' }) {
  const isClass = kind.toLowerCase().split(',').some(value=>value.trim()==='class');
  const fields = isClass ? [['definitions','Definitions'],['properties','Directly declared properties']] : [['definitions','Definitions'],['domains','Declared domains'],['ranges','Declared ranges']];
  return <section aria-label={`${title} concept evidence`}><strong>{title}</strong><dl>{fields.map(([key,label])=><React.Fragment key={key}><dt>{label}</dt><dd>{Array.isArray(value[key]) && value[key].length ? <ul>{value[key].map((item,index)=><li key={index} style={{overflowWrap:'anywhere'}}>{item}</li>)}</ul> : 'Not recorded in this evidence'}</dd></React.Fragment>)}</dl></section>;
}

export default function MergeMappingReview({ sourceId, targetId, sourceLabel, targetLabel, suggestions = [], sourceIri, targetIri, selectedMappings, onSelect, preview, busy, error, dirty = false, compact = false }) {
  const [query, setQuery] = useState('');
  const [onlySelected, setOnlySelected] = useState(false);
  const [minimumScore, setMinimumScore] = useState(0);
  const [page, setPage] = useState(0);
  useEffect(() => { setQuery(''); setOnlySelected(false); setMinimumScore(0); setPage(0); }, [sourceId, targetId]);
  const selections = selectedMappings || (sourceIri && targetIri ? [{source_iri: sourceIri, target_iri: targetIri}] : []);
  const isSelected = row => selections.some(item => item.source_iri === row.source_iri && item.target_iri === row.target_iri);
  const selected = selections.length > 0;
  const rows = suggestions.filter(row => (minimumScore === 0 || (Number.isFinite(row.confidence_score) && row.confidence_score * 100 >= minimumScore)) && (!onlySelected || isSelected(row)) && `${row.source_label} ${row.target_label} ${row.kind} ${row.reason} ${row.source_iri} ${row.target_iri}`.toLowerCase().includes(query.toLowerCase()));
  const conflicts = preview?.conflicts || [];
  const details = <div className="merge-review-workspace">
    {!compact && <header className="merge-review-header"><div><span className="merge-eyebrow">Semantic Bridge / Mapping review</span><h3>2. Review proposed mappings</h3></div><span className="merge-badge">{busy ? 'Request in progress' : dirty ? 'Selection needs validation' : error ? 'Preview failed' : preview ? 'Preview retained' : 'Awaiting agent preview'}</span></header>}
    {!compact && (preview || suggestions.length > 0) && <div className="merge-metrics" aria-label="Merge review summary"><div><span>Proposed pairs</span><strong>{suggestions.length ? suggestions.length.toLocaleString() : preview ? '0' : '—'}</strong></div><div><span>Selected consolidations</span><strong>{selected ? `${selections.length} ${selections.length === 1 ? 'pair' : 'pairs'}` : 'None'}</strong></div><div><span>Unresolved conflicts</span><strong>{preview ? conflicts.length : '—'}</strong></div><div><span>Merged statements</span><strong>{preview?.triple_count == null ? '—' : preview.triple_count.toLocaleString()}</strong></div></div>}
    {error && <div className="merge-notice error" role="alert"><strong>Agent preview did not complete</strong><p>{error}</p><p>Mapping approval unavailable.</p></div>}

    <section className="merge-proposals" aria-label="Agent mapping proposals">
      {preview?.matching_report?.truncated && <p role="status">Mapping search limited.</p>}
      {(preview || suggestions.length > 0) ? <>
      <div className="merge-toolbar"><label>Minimum similarity % <input aria-label="Minimum mapping similarity" type="number" min="0" max="100" value={minimumScore} onChange={event => {setMinimumScore(Math.min(100,Math.max(0,Number(event.target.value) || 0)));setPage(0);}} /></label><input aria-label="Search proposed mappings" placeholder="Search source, target or rationale" value={query} onChange={event => { setQuery(event.target.value); setPage(0); }} /><label><input type="checkbox" checked={onlySelected} onChange={event => { setOnlySelected(event.target.checked); setPage(0); }} /> Selected only</label><button type="button" disabled={!selected || busy} onClick={() => onSelect(null)}>Clear selection</button></div>
      <div className="merge-table-scroll"><table><caption className="merge-sr-only">Agent proposed source to target consolidations</caption><thead><tr><th>Source term</th><th>Target term</th><th>Ontology kind and rationale</th><th>Similarity evidence</th><th>Consolidation</th></tr></thead><tbody>{rows.slice(page * 20, (page + 1) * 20).map(row => { const chosen = isSelected(row); return <tr key={`${row.source_iri}:${row.target_iri}`} className={chosen ? 'selected' : ''}><td><Term label={row.source_label} iri={row.source_iri} /></td><td><Term label={row.target_label} iri={row.target_iri} /></td><td><span className="merge-badge">{row.kind}</span><p>{rationale(row)}</p><p>Equivalence not established</p>{(row.source_evidence || row.target_evidence) && <details><summary>Compare concept evidence</summary><ConceptEvidence title="Source" kind={row.kind} value={row.source_evidence}/><ConceptEvidence title="Target" kind={row.kind} value={row.target_evidence}/></details>}</td><td><strong>{Number.isFinite(row.confidence_score) ? `${Math.round(row.confidence_score * 100)}% similarity` : "Score unavailable"}</strong>{row.ambiguous && <p role="status">Ambiguous alternative</p>}{row.score_components && <details><summary>Score details</summary><table><caption>Recorded similarity calculation</caption><thead><tr><th>Signal</th><th>Similarity</th><th>Weight</th><th>Score contribution</th></tr></thead><tbody>{similarityParts(row,preview?.matching_report).map(part=><tr key={part.name}><td>{part.name.replaceAll('_',' ')}</td><td>{Math.round(part.value*100)}%</td><td>{Number.isFinite(part.weight)?`${Math.round(part.weight*100)}%`:'Not recorded'}</td><td>{Number.isFinite(part.weight)?`${(part.value*part.weight*100).toFixed(1)} points`:'Not recorded'}</td></tr>)}</tbody></table></details>}</td><td><button type="button" aria-pressed={chosen} disabled={busy || (!chosen && selections.length >= 200 && !selections.some(item => item.source_iri === row.source_iri))} onClick={() => onSelect(selectedMappings ? row : chosen ? null : row)}>{chosen ? 'Selected — remove' : 'Select for consolidation'}</button></td></tr>; })}</tbody></table>{!rows.length && <div className="merge-empty"><strong>{!preview && !suggestions.length ? 'Generate an agent preview to see proposed mappings' : 'No proposed mappings match this view'}</strong></div>}</div>
      <div className="merge-pagination"><span>{rows.length} matching proposals · 20 per page</span><button type="button" disabled={!page} onClick={() => setPage(value => value - 1)}>Previous</button><button type="button" disabled={(page + 1) * 20 >= rows.length} onClick={() => setPage(value => value + 1)}>Next</button></div>
      </> : <div className="merge-empty"><strong>Generate an agent preview to see proposed mappings</strong></div>}
      {selected && <div className="merge-notice"><strong>Selected identity changes ({selections.length}/200)</strong>{selections.map(row => <div key={row.source_iri}><Term label="Source" iri={row.source_iri} /><span>will be consolidated into</span><Term label="Target" iri={row.target_iri} /></div>)}<p>Generate a new review plan to validate this selection before approval.</p></div>}
      {conflicts.length > 0 && <div className="merge-notice error"><strong>{conflicts.length} conflicts block approval</strong><details><summary>Inspect conflict evidence</summary><pre>{JSON.stringify(conflicts, null, 2)}</pre></details></div>}
      {preview?.changes && <div className="merge-notice"><strong>Impact against the target ontology</strong><p>{preview.changes.added} statements added · {preview.changes.removed} removed · {preview.changes.unchanged} unchanged · {preview.changes.modified_entity_count} identities consolidated.</p></div>}
    </section>

  </div>;
  if (!compact) return details;
  const scores = suggestions.map(row=>row.confidence_score).filter(value=>Number.isFinite(value)&&value>=0&&value<=1);
  const mean = scores.length ? `${Math.round(scores.reduce((sum,value)=>sum+value,0)/scores.length*100)}%` : 'Not recorded';
  const blocked = dirty || !preview?.publish_recommended;
  const pending = preview?.background_validation && ['queued','preparing','validating'].includes(preview.job_status);
  const reason = preview?.owl_dl_evidence?.reason || preview?.semantic_support?.reason;
  const outcome = !preview ? 'Generate a mapping plan' : dirty ? 'Selection needs validation' : pending ? 'Validation pending' : reason === 'unparsed_rdf_statements' ? 'Publication blocked: logical validation cannot process all statements' : preview.owl_dl_evidence?.status === 'unknown' ? 'Logical consistency unverified' : blocked ? 'Merge needs review' : 'Merge available for CR/CO review';
  return <section className="merge-review-workspace" aria-label="Merge decision output">
    <h3>Source → target mapping review</h3>
    <p><strong>{outcome}</strong></p>
    {preview && <p>{sourceLabel || 'Source vocabulary'} + {targetLabel || 'target vocabulary'}: combined draft prepared. {preview.changes?.modified_entity_count || 0} concept identities consolidated. Source ontologies retained.</p>}
    <p><strong>Mean proposal similarity: {mean}</strong> · {suggestions.length} proposed pairs · {selections.length} selected · {conflicts.length} conflicts</p>
    {error && <p role="alert">{error}</p>}
    <details><summary>View merge details</summary>{details}</details>
  </section>;
}
