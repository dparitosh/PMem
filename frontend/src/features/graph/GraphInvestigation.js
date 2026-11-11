import React, { useState } from 'react';
import ReadGoalPanel from '../../Components/ReadGoalPanel';
import { resolveNodeName, resolveNodeType } from './graphRenderingPolicy';

// View-only scopes are not registered ontologies, so the agent must not receive them as ontology_id.
const NON_ONTOLOGY_SCOPES = new Set(['ALL', 'archimate', 'step', 'mbse_instances']);

export default function GraphInvestigation({ node, ontologyId, nodeCount, relationshipCount, page = 'graph' }) {
  const [question, setQuestion] = useState('Explain this object and its source-provided connections. Identify missing evidence before drawing a business conclusion.');

  const id = node?.elementId;
  const context = { page, ...(id ? {node_id: String(id)} : {}),
    ...(ontologyId && !NON_ONTOLOGY_SCOPES.has(ontologyId) ? {ontology_id: String(ontologyId).replace(/_instances$/, '')} : {}),
    visible_node_count: nodeCount, visible_relationship_count: relationshipCount };
  const task = id && question.trim() ? `${question.trim()}\nFocus on graph node ID ${id} (${resolveNodeName(node)}). ${page === 'modeling' ? 'This selection is an imported model/RDF element, not necessarily a manufactured business instance. Do not equate a class, design or requirement with a physical part or proof of satisfaction. ' : ''}Use registered read tools and cite the returned node/relationship IDs and source evidence. Distinguish direct source references, semantic mappings and inferred conclusions. The displayed graph is a bounded slice (${nodeCount} nodes, ${relationshipCount} relationships); do not treat absent links as proof of no impact. Report gaps and tool failures explicitly. Do not publish or alter data.` : '';
  return <details className="graph-investigation"><summary>Investigate with agent {id ? `· ${resolveNodeName(node)}` : '· select a node'}</summary>
    {!id ? <p>Click a graph node or choose a focused search result to investigate its context.</p> : <>
      <p><strong>{resolveNodeName(node)}</strong> · {node?.properties?.part_type || node?.properties?.source_element_name || resolveNodeType(node)}</p>
      {page === 'modeling' && <label>Engineering task<select defaultValue="" onChange={event => { if (event.target.value) setQuestion(event.target.value); }}>
        <option value="">Choose a task or enter a question</option>
        <option value="Explain this model element using the selected ontology vocabulary, descriptions and recorded relationships. Separate declared facts from inferred conclusions.">Explain model context</option>
        <option value="Trace recorded requirement, function and component relationships for this element. Cite each path and identify missing traceability; do not claim satisfaction without evidence.">Review engineering traceability</option>
        <option value="Investigate recorded dependencies that should be reviewed if this model element changes. Separate model dependencies from physical assembly usage, and identify unknown coverage.">Review change dependencies</option>
        <option value="Find retained decisions relevant to this element and source revision, then verify their supporting graph evidence. Treat past advice as advisory; report when no matching retained decision exists.">Review prior decision evidence</option>
      </select></label>}
      <label>Business question<textarea value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} rows={2}/></label>
      <p>Read-only investigation. Findings need source evidence; this does not approve a change or establish complete impact coverage.</p>
      <ReadGoalPanel key={JSON.stringify([id,ontologyId])} agent="graph-analyst" task={task} context={context} compact startLabel="Investigate selected object" disabled={!task}/>
    </>}
  </details>;
}
