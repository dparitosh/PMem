import axios from 'axios';
import { buildUrl } from '../config';
import { serviceAuthHeaders } from './serviceAuth';
import agenticAPI from './agenticApi';
import { agentToolResult, validBridgePolicy } from './agentToolResult';

// Dedicated client: approval credentials must never enter the debug-logging
// interceptors used by the generic legacy API client.
const client = axios.create({ timeout: 150000 });
client.interceptors.request.use((request) => {
  request.headers = request.headers || {};
  const credentials = serviceAuthHeaders(request.url, request.method);
  const explicit = request.headers.get?.('Authorization') || request.headers.Authorization;
  if (explicit || request.headers.get?.('X-API-Key') || request.headers['X-API-Key']) { delete credentials.Authorization; delete credentials['X-API-Key']; }
  Object.assign(request.headers, credentials);
  return request;
});
const root = '/api/v1/workflows/bridge';
const auth = (token) => ({ headers: { ...serviceAuthHeaders(), ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
export const bridgeApi = {
  automate: (ontologyId, importId, identity, manualMappings = [], candidateOffset = 0) => agenticAPI.runWorkflow(
    'bridge-validated-automation', {}, {...identity, step_inputs:[{ontology_id:ontologyId,import_task_id:importId,manual_mappings:manualMappings,candidate_offset:candidateOffset},{},{}]}),
  automationStatus: (id) => agenticAPI.getRun(id, 'workflow'),
  evaluate: async (id) => {
    const response = await agenticAPI.runAgent('ontology-steward', 'bridge.mapping.evaluate', {preview_id:id});
    const run = agentToolResult(response, 'ontology-steward', 'bridge.mapping.evaluate');
    if (!validBridgePolicy(run.result,id)) throw new Error('Steward returned an incompatible policy decision for this saved preview.');
    return {data:{...run.result, agent_run_id:run.runId}};
  },
  publishAutomatic: async (id, identity) => {
    const response = await agenticAPI.runAgent('ontology-governor', 'bridge.mapping.publish_automatic', {preview_id:id}, identity);
    const run = agentToolResult(response, 'ontology-governor', 'bridge.mapping.publish_automatic');
    return {data:{...run.result, agent_run_id:run.runId}};
  },
  preview: async (ontologyId, importId, identity, manualMappings = [], candidateOffset = 0) => {
    const response = await agenticAPI.runAgent('ontology-governor', 'bridge.mapping.preview',
      { ontology_id: ontologyId, import_task_id: importId, manual_mappings: manualMappings, candidate_offset:candidateOffset }, identity);
    const run = agentToolResult(response, 'ontology-governor', 'bridge.mapping.preview');
    return { data: { ...run.result, agent_run_id: run.runId } };
  },
  status: (id, token) => client.get(buildUrl(`${root}/jobs/${encodeURIComponent(id)}`), auth(token)),
  publish: async (id, approvedIds, identity) => {
    const response = await agenticAPI.runAgent('ontology-governor', 'bridge.mapping.publish',
      { preview_id: id, approved_candidate_ids: approvedIds }, identity);
    const run = agentToolResult(response, 'ontology-governor', 'bridge.mapping.publish');
    return { data: { ...run.result, agent_run_id: run.runId } };
  },
  artifact: (id, token) => client.get(buildUrl(`${root}/jobs/${encodeURIComponent(id)}/artifact`),
    { ...auth(token), responseType: 'blob' }),
};
