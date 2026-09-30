import axios from 'axios';
import { config, API, buildSemanticServiceUrl, replaceParams } from '../config';
import { serviceAuthHeaders } from './serviceAuth';

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
  if (!explicit) Object.assign(requestConfig.headers, serviceAuthHeaders());
  return requestConfig;
}

agenticClient.interceptors.request.use(applyAgenticAuth);

function agenticUrl(endpoint) {
  return buildSemanticServiceUrl('agentic', endpoint);
}

export const agenticAPI = {
  isEnabled: () => true,
  isConfigured: () => Boolean(config.semanticServiceUrls?.agentic),
  health: (options = {}) => agenticClient.get(agenticUrl(API.agentic.health), options),
  listAgents: (options = {}) => agenticClient.get(agenticUrl(API.agentic.agents), options),
  listTools: (options = {}) => agenticClient.get(agenticUrl(API.agentic.tools), options),
  importOpenApi: (document, sourceName = '') => agenticClient.post(
    agenticUrl(API.agentic.openApiImport),
    { document, source_name: sourceName },
  ),
  runAgent: (agentName, inputs = {}) => agenticClient.post(
    agenticUrl(replaceParams(API.agentic.runAgent, { agent_name: agentName })),
    { inputs },
  ),
  runWorkflow: (workflowId, inputs = {}) => agenticClient.post(
    agenticUrl(API.agentic.runWorkflow),
    { workflow_id: workflowId, inputs },
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
