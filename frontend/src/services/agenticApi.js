import axios from 'axios';
import { reportRunRecovery } from './runRecovery';
import { config, API, buildSemanticServiceUrl } from '../config';
import { serviceAuthHeaders, handleSessionRejection } from './serviceAuth';

const agenticClient = axios.create({
  baseURL: undefined,
  timeout: config.requestTimeout || 300000,
  headers: { 'Content-Type': 'application/json' },
});

export function applyAgenticAuth(requestConfig) {
  requestConfig.headers = requestConfig.headers || {};
  // A call may provide a scoped credential (for example, the ontology review
  // read token). Keep it ahead of the app-wide bootstrap token.
  const explicit = requestConfig.headers.get?.('Authorization') || requestConfig.headers.Authorization;
  const credentials = serviceAuthHeaders(requestConfig.url, requestConfig.method);
  if (explicit || requestConfig.headers.get?.('X-API-Key') || requestConfig.headers['X-API-Key']) { delete credentials.Authorization; delete credentials['X-API-Key']; }
  Object.assign(requestConfig.headers, credentials);
  return requestConfig;
}

agenticClient.interceptors.request.use(applyAgenticAuth);
agenticClient.interceptors.response.use(response => response, error => {
  const authorization = error.config?.headers?.get?.('Authorization') || error.config?.headers?.Authorization || error.config?.headers?.authorization || '';
  handleSessionRejection(error.response?.status, authorization, error.response?.data?.detail);
  reportRunRecovery(error); return Promise.reject(error);
});

function agenticUrl(endpoint) {
  return buildSemanticServiceUrl('agentic', endpoint);
}

export const agenticAPI = {
  getRun: (id, kind = 'workflow') => agenticClient.get(agenticUrl(`/api/v1/${kind === 'dt' ? 'integrations/dt-requirements-design/runs' : kind === 'workflow' ? 'workflow-runs' : 'runs'}/${encodeURIComponent(id)}`)),
  isEnabled: () => true,
  isConfigured: () => Boolean(config.semanticServiceUrls?.agentic),
  health: (options = {}) => agenticClient.get(agenticUrl(API.agentic.health), options),
  listAgents: (options = {}) => agenticClient.get(agenticUrl(API.agentic.agents), options),
  listTools: (options = {}) => agenticClient.get(agenticUrl(API.agentic.tools), options),
  runAgent: (agentId, toolId, inputs = {}, approval = {}, options = {}) => agenticClient.post(
    agenticUrl(API.agentic.runAgent),
    { agent_id: agentId, tool_id: toolId, inputs,
      approved_by: approval.approved_by, approval_token: approval.approval_token },
    options,
  ),
  runWorkflow: (workflowId, inputs = {}, execution = {}, options = {}) => agenticClient.post(
    agenticUrl(API.agentic.runWorkflow),
    { workflow_id: workflowId, inputs, step_inputs: execution.step_inputs,
      approved_by: execution.approved_by, approval_token: execution.approval_token },
    options,
  ),
  orchestrateOntology: (payload = {}, options = {}) => agenticClient.post(
    agenticUrl(API.agentic.orchestrateOntology),
    payload,
    options,
  ),
  observabilitySummary: (options = {}) => agenticClient.get(agenticUrl(API.agentic.observabilitySummary), options),
  observabilityRuns: (limit = 20, options = {}) => agenticClient.get(
    agenticUrl(API.agentic.observabilityRuns),
    { ...options, params: { ...(options.params || {}), limit } },
  ),
};

export { agenticClient };
export default agenticAPI;
