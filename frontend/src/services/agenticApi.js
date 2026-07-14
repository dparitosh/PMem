import axios from 'axios';
import { config, API, replaceParams } from '../config';

const agenticClient = axios.create({
  baseURL: config.agenticServiceUrl || undefined,
  timeout: config.requestTimeout || 300000,
  headers: { 'Content-Type': 'application/json' },
});

function requireConfiguredService() {
  if (!config.agenticEnabled) {
    throw new Error('Ontology agentic service is disabled. Set REACT_APP_AGENTIC_ENABLED=true to enable it.');
  }
  if (!config.agenticServiceUrl) {
    throw new Error('Ontology agentic service is not configured. Set REACT_APP_AGENTIC_SERVICE_URL.');
  }
}

function agenticUrl(endpoint) {
  requireConfiguredService();
  return `${config.agenticServiceUrl}${endpoint}`;
}

export const agenticAPI = {
  isEnabled: () => Boolean(config.agenticEnabled),
  isConfigured: () => Boolean(config.agenticEnabled && config.agenticServiceUrl),
  health: () => agenticClient.get(agenticUrl(API.agentic.health)),
  listAgents: () => agenticClient.get(agenticUrl(API.agentic.agents)),
  listTools: () => agenticClient.get(agenticUrl(API.agentic.tools)),
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
};

export { agenticClient };
export default agenticAPI;
