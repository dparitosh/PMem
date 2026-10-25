import React, { useState } from 'react';
import ReadGoalPanel from '../../Components/ReadGoalPanel';
import { resolveNodeName, resolveNodeType } from './graphRenderingPolicy';

export default function GraphInvestigation({ node, ontologyId, nodeCount, relationshipCount }) {
  const [question, setQuestion] = useState('Explain this object and its source-provided connections. Identify missing evidence before drawing a business conclusion.');
  const id = node?.elementId;
  const context = { page: 'graph', ...(id ? {node_id: String(id)} : {}),
    ...(ontologyId && !['ALL','archimate'].includes(ontologyId) ? {ontology_id: ontologyId} : {}),
    visible_node_count: nodeCount, visible_relationship_count: relationshipCount };
  const task = id && question.trim() ? `${question.trim()}\nFocus on graph node ID ${id} (${resolveNodeName(node)}). Use registered read tools and cite the returned node/relationship IDs and source evidence. Distinguish direct source references, semantic mappings and inferred conclusions. The displayed graph is a bounded slice (${nodeCount} nodes, ${relationshipCount} relationships); do not treat absent links as proof of no impact. Report gaps and tool failures explicitly. Do not publish or alter data.` : '';
  return <details className="graph-investigation"><summary>Investigate with agent {id ? `· ${resolveNodeName(node)}` : '· select a node'}</summary>
    {!id ? <p>Click a graph node or choose a focused search result to investigate its context.</p> : <>
      <p><strong>{resolveNodeName(node)}</strong> · {node?.properties?.part_type || node?.properties?.source_element_name || resolveNodeType(node)}</p>
      <label>Business question<textarea value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} rows={2}/></label>
      <p>Read-only investigation. Findings need source evidence; this does not approve a change or establish complete impact coverage.</p>
      <ReadGoalPanel key={JSON.stringify([id,ontologyId])} agent="graph-analyst" task={task} context={context} compact startLabel="Investigate selected object" disabled={!task}/>
    </>}
  </details>;
}
