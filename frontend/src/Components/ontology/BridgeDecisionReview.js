import React from 'react';
export default function BridgeDecisionReview({report}) {
 const results=(report?.steps || []).map(step=>step.result).filter(Boolean);
 const plan=results.find(value=>Array.isArray(value.alignment_items));
 if (!plan) return <p role="status">Mapping assessment unavailable.</p>;
 const logical=results.find(value=>Object.prototype.hasOwnProperty.call(value,'consistency_verified'));
 const candidates=plan.alignment_candidates || [];
 const items=plan.alignment_items || [];
 const unmatched=items.filter(item=>item.status==='unmatched').length;
 const invalid=items.filter(item=>item.status==='invalid').length;
 const ambiguous=items.filter(item=>item.status==='ambiguous').length;
 return <section aria-label="Mapping decision summary" className="mapping-review">
  <h4>{candidates.length ? 'Mapping suggestions need review' : 'No name-based match found'}</h4>
  {logical && <p role="status">Logical audit: {logical.consistency_verified === true && logical.deductive_reasoner_executed === true ? logical.status === 'consistent' ? 'Consistency verified; mapping meaning still requires review' : 'Conflicts detected' : 'Unverified; inspect the validation report'}</p>}
  <p>{candidates.length} suggestions · {unmatched} unmatched terms · {invalid + ambiguous} conflicting or ambiguous terms</p>
  {candidates.length > 0 && <table><caption>Name-based suggestions</caption><thead><tr><th>Source</th><th>Suggested target</th><th>Decision</th></tr></thead><tbody>{candidates.slice(0,20).map((item,index)=><tr key={`${item.source}:${item.target_iri}:${index}`}><td>{item.source}</td><td>{item.target_iri?.split(/[#/]/).pop() || 'Not recorded'}</td><td>{item.status==='invalid' ? 'Blocked' : 'Review required'}</td></tr>)}</tbody></table>}
  <p>{candidates.length ? 'Next: prepare mappings for CR/CO review.' : 'Next: review the selected ontology or add a manual mapping.'}</p>
  {plan.candidate_limit_reached && <p role="status">Results limited to the inspected terms.</p>}
 </section>;
}
