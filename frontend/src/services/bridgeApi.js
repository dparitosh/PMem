import axios from 'axios';
import { buildUrl } from '../config';
import { serviceAuthHeaders } from './serviceAuth';
import agenticAPI from './agenticApi';
import { governorResult } from './ontologyMergeAgent';

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
  preview: async (ontologyId, importId, identity, manualMappings = []) => {
    const response = await agenticAPI.runAgent('ontology-governor', 'bridge.mapping.preview',
      { ontology_id: ontologyId, import_task_id: importId, manual_mappings: manualMappings }, identity);
    const run = governorResult(response, 'bridge.mapping.preview');
    return { data: { ...run.result, agent_run_id: run.runId } };
  },
  status: (id, token) => client.get(buildUrl(`${root}/jobs/${encodeURIComponent(id)}`), auth(token)),
  publish: async (id, approvedIds, identity) => {
    const response = await agenticAPI.runAgent('ontology-governor', 'bridge.mapping.publish',
      { preview_id: id, approved_candidate_ids: approvedIds }, identity);
    const run = governorResult(response, 'bridge.mapping.publish');
    return { data: { ...run.result, agent_run_id: run.runId } };
  },
  artifact: (id, token) => client.get(buildUrl(`${root}/jobs/${encodeURIComponent(id)}/artifact`),
    { ...auth(token), responseType: 'blob' }),
};
