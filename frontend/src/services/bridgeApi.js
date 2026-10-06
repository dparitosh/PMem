import axios from 'axios';
import { buildUrl } from '../config';
import { serviceAuthHeaders } from './serviceAuth';

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
  preview: (ontologyId, importId, token) => client.post(buildUrl(`${root}/previews`),
    { ontology_id: ontologyId, import_task_id: importId }, auth(token)),
  status: (id, token) => client.get(buildUrl(`${root}/jobs/${encodeURIComponent(id)}`), auth(token)),
  publish: (id, approvedIds, identity) => client.post(buildUrl(`${root}/previews/${encodeURIComponent(id)}/publish`),
    { approved_candidate_ids: approvedIds, approved_by: identity.approved_by,
      ...(identity.approval_token ? { approval_token: identity.approval_token } : {}) }),
  artifact: (id, token) => client.get(buildUrl(`${root}/jobs/${encodeURIComponent(id)}/artifact`),
    { ...auth(token), responseType: 'blob' }),
};
