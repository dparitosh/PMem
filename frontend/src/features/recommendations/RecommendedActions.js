import React from 'react';
import {businessDisplayName} from './businessDisplayName';

export default function RecommendedActions({service,data}) {
  let rows=[];
  if(service==='change-impact') rows=(data.realization_chain||[]).map(item=>({
    name:item.name,action:item.review_status==='configuration_conflict'?'Check the recorded revision relationship and configuration before authorizing the change.':'Review this dependency and confirm its effective configuration.',
    reason:(item.path_names||[]).map(businessDisplayName).join(' → ')||item.link_type||'Recorded dependency path',
  }));
  if(service==='similar-parts') rows=(data.similar_parts||[]).map(item=>({name:item.name,
    action:'Compare the recorded dimensions, material, units and missing evidence before considering reuse.',
    reason:typeof item.similarity_score==='number'?`Similarity indicator: ${item.similarity_score}; this is not interchangeability approval.`:'Candidate returned by the bounded comparison.'}));
  if(service==='manufacturing') rows=(data.direct_processes||[]).map(item=>({name:item.name||item.process_name,
    action:'Review this recorded process link and verify the operation, sequence and applicable part revision.',reason:'Direct process association; manufacturing readiness still needs review.'}));
  return <section className="recommendation-actions" aria-label="Recommended next actions"><h3>Recommended next actions</h3>
    <p>These are evidence-based review tasks. They do not approve a change or certify reuse.</p>
    {rows.length?<table><thead><tr><th>Business record</th><th>Recommended action</th><th>Why</th></tr></thead><tbody>{rows.slice(0,20).map((row,i)=><tr key={i}><td>{businessDisplayName(row.name)}</td><td>{row.action}</td><td>{row.reason}</td></tr>)}</tbody></table>:<p>No actionable candidates were established in this result. Confirm the selected identity, published links and analysis coverage before drawing a conclusion.</p>}
  </section>;
}
