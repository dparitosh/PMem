import { pageTaskContext } from './pageTasks';
import {prepareSessionRequest,trackSessionRequest,releaseRequest,staleRequest} from './requestSession';
import axios from 'axios';
import { openApiPreview } from './openApiPreview';
import { reportRunRecovery } from './runRecovery';
import { apiRequestId, apiErrorMessage } from '../utils/apiErrorMessage';
import { config, API, buildSemanticServiceUrl } from '../config';
import { serviceAuthHeaders, handleSessionRejection, requireServiceReadAccess } from './serviceAuth';

const agenticClient = axios.create({
  baseURL: undefined,
  timeout: config.requestTimeout || 300000,
  headers: { 'Content-Type': 'application/json' },
});

export function applyAgenticAuth(requestConfig) {
  prepareSessionRequest(requestConfig);
  requestConfig.headers = requestConfig.headers || {};
  if (String(requestConfig.method).toLowerCase() === 'post' && /\/api\/v1\/(runs|workflow-runs)$/.test(String(requestConfig.url).split('?')[0]) && requestConfig.data && typeof requestConfig.data === 'object') {
    requestConfig.data = { ...requestConfig.data, page_context: pageTaskContext(requestConfig.data.page_context || {}) };
  }
  // A call may provide a scoped credential (for example, the ontology review
  // read token). Keep it ahead of the app-wide bootstrap token.
  const explicit = requestConfig.headers.get?.('Authorization') || requestConfig.headers.Authorization || requestConfig.headers.authorization;
  const credentials = serviceAuthHeaders(requestConfig.url, requestConfig.method);
  if (explicit || requestConfig.headers.get?.('X-API-Key') || requestConfig.headers['X-API-Key'] || requestConfig.headers['x-api-key']) { delete credentials.Authorization; delete credentials['X-API-Key']; }
  Object.assign(requestConfig.headers, credentials);
  requireServiceReadAccess(requestConfig);
  trackSessionRequest(requestConfig);
  return requestConfig;
}

agenticClient.interceptors.request.use(applyAgenticAuth);
agenticClient.interceptors.response.use(response => {
  releaseRequest(response.config);
  if(staleRequest(response.config))return Promise.reject(new axios.CanceledError('Discarded agent response from previous credentials'));
  if (String(response.config?.method).toLowerCase() === 'post' && response.data?.run_id) {
    window.dispatchEvent(new CustomEvent('depo:page-task-updated'));
  }
  return response;
}, error => {
  releaseRequest(error.config);
  if(staleRequest(error.config))return Promise.reject(new axios.CanceledError('Credentials changed; previous agent request discarded'));
  error.apiError = { status: error.response?.status, requestId: apiRequestId(error),
    message: apiErrorMessage(error) };
  const authorization = error.config?.headers?.get?.('Authorization') || error.config?.headers?.Authorization || error.config?.headers?.authorization || '';
  const apiKey=error.config?.headers?.get?.('X-API-Key')||error.config?.headers?.['X-API-Key']||error.config?.headers?.['x-api-key']||'';
  handleSessionRejection(error.response?.status, String(apiKey).startsWith('depo_session_')?apiKey:authorization, error.response?.data?.detail);
  reportRunRecovery(error); return Promise.reject(error);
});

function agenticUrl(endpoint) {
  return buildSemanticServiceUrl('agentic', endpoint);
}

export const agenticAPI = {
  pageTasks: (page, offset = 0, options = {}) => agenticClient.get(agenticUrl('/api/v1/page-tasks'), { ...options, params: {page,offset,limit:20} }),
  pageTask: (kind, id, options = {}) => agenticClient.get(agenticUrl(`/api/v1/page-tasks/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`), options),
  importOpenApi: async (document, filename) => ({ data: openApiPreview(document, filename) }),
  controlWorkflow: (id, action, options = {}) => agenticClient.post(agenticUrl(`/api/v1/workflow-runs/${encodeURIComponent(id)}/control`), { action }, options),
  recoverWorkflow: (id, identity, options = {}) => agenticClient.post(agenticUrl(`/api/v1/workflow-runs/${encodeURIComponent(id)}/recover`), identity, options),
  reconcileWorkflowReceipt: (id, identity, options = {}) => agenticClient.post(agenticUrl(`/api/v1/workflow-runs/${encodeURIComponent(id)}/reconcile-receipt`), identity, options),
  getRun: (id, kind = 'workflow', options = {}) => agenticClient.get(agenticUrl(`/api/v1/${kind === 'dt' ? 'integrations/dt-requirements-design/runs' : kind === 'workflow' ? 'workflow-runs' : 'runs'}/${encodeURIComponent(id)}`), options),
  isEnabled: () => true,
  isConfigured: () => Boolean(config.semanticServiceUrls?.agentic),
  health: (options = {}) => agenticClient.get(agenticUrl(API.agentic.health), options),
  listAgents: (options = {}) => agenticClient.get(agenticUrl(API.agentic.agents), options),
  listTools: (options = {}) => agenticClient.get(agenticUrl(API.agentic.tools), options),
  runAgent: (agentId, toolId, inputs = {}, approval = {}, options = {}) => agenticClient.post(
    agenticUrl(API.agentic.runAgent),
    { agent_id: agentId, tool_id: toolId, inputs,
      approved_by: approval.approved_by, approval_token: approval.approval_token },
    { timeout: 3660000, ...options },
  ),
  runWorkflow: (workflowId, inputs = {}, execution = {}, options = {}) => agenticClient.post(
    agenticUrl(API.agentic.runWorkflow),
    { workflow_id: workflowId, inputs, step_inputs: execution.step_inputs,
      approved_by: execution.approved_by, approval_token: execution.approval_token },
    { timeout: 3660000, ...options },
  ),
  orchestrateOntology: (payload = {}, options = {}) => agenticClient.post(
    agenticUrl(API.agentic.orchestrateOntology),
    payload,
    { timeout: Math.max(config.chatStreamTimeout || 1200000, 1200000), ...options },
  ),
  observabilitySummary: (options = {}) => agenticClient.get(agenticUrl(API.agentic.observabilitySummary), options),
  observabilityRuns: (limit = 20, options = {}) => agenticClient.get(
    agenticUrl(API.agentic.observabilityRuns),
    { ...options, params: { ...(options.params || {}), limit } },
  ),
};

export { agenticClient };
export default agenticAPI;
