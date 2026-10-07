import agenticAPI from './agenticApi';
import { getCredentialProfile } from './serviceAuth';

export function governorResult(response, tool) {
  const run = response.data;
  if (!run?.result || typeof run.result !== 'object' || run.agent_id !== 'ontology-governor' || run.tool_id !== tool) {
    throw new Error('Agent returned an incompatible result. Inspect agent telemetry before retrying.');
  }
  return { result: run.result, runId: run.run_id };
}

async function execute(tool, inputs, approvedBy) {
  const actor = approvedBy.trim();
  const token = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
  if (!actor || !token) throw new Error('Enter the approving steward and connect governed agent access in Admin.');
  const response = await agenticAPI.runAgent('ontology-governor', tool, inputs,
    { approved_by: actor, approval_token: token });
  return governorResult(response, tool);
}

export const ontologyMergeAgent = {
  preview: (sources, options, actor) => execute('ontology.merge.preview', { source_ontology_ids: sources, ...options }, actor),
  apply: (previewId, actor) => execute('ontology.merge.apply', { preview_id: previewId }, actor),
};
