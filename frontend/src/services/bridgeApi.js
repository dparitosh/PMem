import axios from 'axios';
import { buildUrl } from '../config';

// Dedicated client: approval credentials must never enter the debug-logging
// interceptors used by the generic legacy API client.
const client = axios.create({ timeout: 150000 });
const root = '/api/v1/workflows/bridge';
const auth = (token) => ({ headers: token ? { Authorization: `Bearer ${token}` } : {} });
export const bridgeApi = {
  preview: (ontologyId, importId, token) => client.post(buildUrl(`${root}/previews`),
    { ontology_id: ontologyId, import_task_id: importId }, auth(token)),
  status: (id, token) => client.get(buildUrl(`${root}/jobs/${encodeURIComponent(id)}`), auth(token)),
  publish: (id, approvedIds, identity) => client.post(buildUrl(`${root}/previews/${encodeURIComponent(id)}/publish`),
    { approved_candidate_ids: approvedIds, ...(identity.approval_token ? identity : {}) }),
  artifact: (id, token) => client.get(buildUrl(`${root}/jobs/${encodeURIComponent(id)}/artifact`),
    { ...auth(token), responseType: 'blob' }),
};
