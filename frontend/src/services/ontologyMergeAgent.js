import agenticAPI from './agenticApi';
import { getCredentialProfile } from './serviceAuth';

export function governorResult(response, tool) {
  const run = response.data;
  if (!run?.result || typeof run.result !== 'object' || Array.isArray(run.result) ||
      typeof run.run_id !== 'string' || !run.run_id || (run.status && run.status !== 'completed') ||
      run.agent_id !== 'ontology-governor' || run.tool_id !== tool) {
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
  apply: async (previewId, actor) => {
    const response = await execute('ontology.merge.apply', { preview_id: previewId, publish: true }, actor);
    const result = response.result;
    const ontologyId = result.ontology?.ontology_id;
    const publication = result.publication;
    const receipt = publication?.receipt;
    if (result.status === 'merged' && result.preview_id === previewId && ontologyId &&
        ['queued', 'running'].includes(result.publication_status) && publication?.status === result.publication_status &&
        publication.ontology_id === ontologyId && typeof publication.job_id === 'string' && publication.job_id) {
      return response;
    }
    if (result.status !== 'merged' || result.preview_id !== previewId || !ontologyId || result.publication_status !== 'published' ||
        publication?.status !== 'published' || publication.ontology_id !== ontologyId || !publication.publication_id ||
        receipt?.status !== 'published' || receipt.current !== true || receipt.ontology_id !== ontologyId || receipt.publication_id !== publication.publication_id ||
        ['resources','relationships'].some(field => !Number.isInteger(receipt[field]) || receipt[field] < 0) ||
        (publication.artifact_sha256 && publication.artifact_sha256 !== publication.publication_id)) {
      throw new Error('Merge publication receipt is unverified. Retry the same reviewed preview to reconcile its result.');
    }
    return response;
  },
};
