/**
 * API Configuration - Centralized endpoint mapping
 * All backend API endpoints are configured here via environment variables
 * This allows easy switching between environments without code changes
 */

const configuredBackendUrl = process.env.REACT_APP_BACKEND_URL;
const configuredAgenticServiceUrl = process.env.REACT_APP_AGENTIC_SERVICE_URL;

const resolveBackendUrl = () => {
  const fallbackHost = typeof window !== 'undefined' && window.location?.hostname
    ? window.location.hostname
    : '127.0.0.1';
  const fallback = `http://${fallbackHost}:8000`;
  if (!configuredBackendUrl) return fallback;

  try {
    const configured = new URL(configuredBackendUrl);
    const browserHost = typeof window !== 'undefined' ? window.location?.hostname : '';
    const isLocalConfigured = configured.hostname === 'localhost' || configured.hostname === '127.0.0.1';
    const isRemoteBrowser = browserHost && browserHost !== 'localhost' && browserHost !== '127.0.0.1';
    if (isLocalConfigured && isRemoteBrowser) {
      configured.hostname = browserHost;
      return configured.toString().replace(/\/$/, '');
    }
  } catch (_err) {
    return fallback;
  }

  return configuredBackendUrl;
};

// Base configuration
const baseConfig = {
  backendUrl: resolveBackendUrl(),
  agenticServiceUrl: (configuredAgenticServiceUrl || '').replace(/\/$/, ''),
  apiVersion: process.env.REACT_APP_API_VERSION || 'v1',
  environment: process.env.REACT_APP_ENV || 'development',
  debug: process.env.REACT_APP_DEBUG === 'true',
  logLevel: process.env.REACT_APP_LOG_LEVEL || 'info',
  requestTimeout: parseInt(process.env.REACT_APP_REQUEST_TIMEOUT || '300000', 10),
};

// Deprecated: Keep old property for backward compatibility
const config = {
  ...baseConfig,
  apiUrl: baseConfig.backendUrl,
};

/**
 * Health & Status Endpoints
 */
const HEALTH_ENDPOINTS = {
  health: process.env.REACT_APP_API_HEALTH || '/health',
  ready: process.env.REACT_APP_API_READY || '/ready',
  graphMetrics: process.env.REACT_APP_API_GRAPH_METRICS || '/graph-metrics',
  ontologiesAvailable: process.env.REACT_APP_API_ONTOLOGIES_AVAILABLE || '/ontologies/available',
  neo4jHealth: process.env.REACT_APP_API_NEO4J_HEALTH || '/health/neo4j',
};

/**
 * Graph Visualization Endpoints
 */
const GRAPH_ENDPOINTS = {
  graphvis: process.env.REACT_APP_API_GRAPHVIS || '/graphvis',
  graphvisByOntology: process.env.REACT_APP_API_GRAPHVIS_BY_ONTOLOGY || '/graphvis/by-ontology/{prefix}',
  graphView: process.env.REACT_APP_API_GRAPH_VIEW || '/api/v1/graph/view',
  graphOntologyView: process.env.REACT_APP_API_GRAPH_ONTOLOGY_VIEW || '/api/v1/graph/view/ontology/{prefix}',
  graphArchitectureView: process.env.REACT_APP_API_GRAPH_ARCHITECTURE_VIEW || '/api/v1/graph/view/architecture/{prefix}',
  contextualSubgraph: process.env.REACT_APP_API_CONTEXTUAL_SUBGRAPH || '/api/v1/graph/contextual-subgraph',
  ontologiesList: process.env.REACT_APP_API_ONTOLOGIES_LIST || '/ontologies/list',
  neo4jHealth: process.env.REACT_APP_API_NEO4J_HEALTH || '/health/neo4j',
  graphfilter: process.env.REACT_APP_API_GRAPHFILTER || '/graphfilter',
  graphfilterMulti: process.env.REACT_APP_API_GRAPHFILTER_MULTI || '/graphfilter-multi',
  graphtraverse: process.env.REACT_APP_API_GRAPHTRAVERSE || '/graphtraverse',
  graphtraverseNode: process.env.REACT_APP_API_GRAPHTRAVERSE_NODE || '/graphtraverse/{node_id}',
  comparativeSearch: process.env.REACT_APP_API_COMPARATIVE_SEARCH || '/comparative-search',
  schemaGraph: process.env.REACT_APP_API_SCHEMA_GRAPH || '/schema-graph',
  instanceGraph: process.env.REACT_APP_API_INSTANCE_GRAPH || '/instance-graph',
  stepParts: process.env.REACT_APP_API_STEP_PARTS || '/ontology/step/parts',
  ontologyGraph: process.env.REACT_APP_API_ONTOLOGY_GRAPH || '/ontology/{ontology}',
  ontologyGraphByType: process.env.REACT_APP_API_ONTOLOGY_GRAPH_BY_TYPE || '/ontology/{ontology_type}',
  ontologyInstances: process.env.REACT_APP_API_ONTOLOGY_INSTANCES || '/ontology/{ontology}/instances',
  ontologyInstancesByType: process.env.REACT_APP_API_ONTOLOGY_INSTANCES_BY_TYPE || '/ontology/{ontology_type}/instances',
  ontologyStepPart: process.env.REACT_APP_API_ONTOLOGY_STEP_PART || '/ontology/step/{part}',
  ontologyStepPartByName: process.env.REACT_APP_API_ONTOLOGY_STEP_PART_BY_NAME || '/ontology/step/{part_name}',
  ontologyMbseInstances: process.env.REACT_APP_API_ONTOLOGY_MBSE_INSTANCES || '/ontology/mbse-instances',
  ontologyOptions: process.env.REACT_APP_API_ONTOLOGY_OPTIONS || '/ontology/options',
  ontologyRegisteredRoot: process.env.REACT_APP_API_ONTOLOGY_REGISTERED_ROOT || '/ontology/registered',
};

/**
 * Schema & Metadata Endpoints
 */
const SCHEMA_ENDPOINTS = {
  schema: process.env.REACT_APP_API_SCHEMA || '/schema',
  ap242RotorPmi: process.env.REACT_APP_API_AP242_ROTOR_PMI || '/ap242/rotor-shaft-pmi',
  ap242Search: process.env.REACT_APP_API_AP242_SEARCH || '/ap242/search',
  reports: process.env.REACT_APP_API_REPORTS || '/reports',
};

/**
 * Chat & Conversation Endpoints
 */
const CHAT_ENDPOINTS = {
  chat: process.env.REACT_APP_API_CHAT || '/chat',
  chatStream: process.env.REACT_APP_API_CHAT_STREAM || '/chat-stream',
  validate: process.env.REACT_APP_API_CHAT_VALIDATE || '/chat/validate',
  jobs: process.env.REACT_APP_API_CHAT_JOBS || '/chat/jobs',
  jobStatus: process.env.REACT_APP_API_CHAT_JOB_STATUS || '/chat/jobs/{job_id}',
  health: process.env.REACT_APP_API_CHAT_HEALTH || '/chat/health',
  status: process.env.REACT_APP_API_CHAT_STATUS || '/chat/status',
  capabilities: process.env.REACT_APP_API_CHAT_CAPABILITIES || '/chat/capabilities',
  sampleQueries: process.env.REACT_APP_API_CHAT_SAMPLE_QUERIES || '/chat/sample-queries',
};

/**
 * Ontology Management Endpoints (v1)
 */
const ONTOLOGY_ENDPOINTS = {
  upload: process.env.REACT_APP_API_ONTOLOGY_UPLOAD || '/api/v1/ontology/upload',
  registered: process.env.REACT_APP_API_ONTOLOGY_REGISTERED || '/api/v1/ontology/registered',
  get: process.env.REACT_APP_API_ONTOLOGY_GET || '/api/v1/ontology',
  taxonomy: process.env.REACT_APP_API_ONTOLOGY_TAXONOMY || '/api/v1/ontology/{ontology}/taxonomy',
  reason: process.env.REACT_APP_API_ONTOLOGY_REASON || '/api/v1/ontology/{ontology}/reason',
  inferencePreview: process.env.REACT_APP_API_ONTOLOGY_INFERENCE_PREVIEW || '/api/v1/ontology/{ontology}/inference/preview',
  skosValidate: process.env.REACT_APP_API_ONTOLOGY_SKOS_VALIDATE || '/api/v1/ontology/semantic/skos/validate',
  skosSearch: process.env.REACT_APP_API_ONTOLOGY_SKOS_SEARCH || '/api/v1/ontology/semantic/skos/search',
  skosTraverse: process.env.REACT_APP_API_ONTOLOGY_SKOS_TRAVERSE || '/api/v1/ontology/semantic/skos/traverse',
  skosStoragePlan: process.env.REACT_APP_API_ONTOLOGY_SKOS_STORAGE_PLAN || '/api/v1/ontology/semantic/skos/storage-plan',
  ruleValidate: process.env.REACT_APP_API_ONTOLOGY_RULE_VALIDATE || '/api/v1/ontology/semantic/rules/validate',
  ruleExecutePreview: process.env.REACT_APP_API_ONTOLOGY_RULE_EXECUTE_PREVIEW || '/api/v1/ontology/semantic/rules/execute-preview',
  ruleMaterializationPlan: process.env.REACT_APP_API_ONTOLOGY_RULE_MATERIALIZATION_PLAN || '/api/v1/ontology/semantic/rules/materialization-plan',
  dataDictionary: process.env.REACT_APP_API_ONTOLOGY_DATA_DICTIONARY || '/api/v1/ontology/{ontology}/data-dictionary',
  prefixDataDictionary: process.env.REACT_APP_API_ONTOLOGY_PREFIX_DATA_DICTIONARY || '/api/v1/ontology/{prefix}/data-dictionary',
  mappings: process.env.REACT_APP_API_ONTOLOGY_MAPPINGS || '/api/v1/ontology/{ontology}/mappings/{type}',
  prefixMappings: process.env.REACT_APP_API_ONTOLOGY_PREFIX_MAPPINGS || '/api/v1/ontology/{prefix}/mappings/{source_format}',
  mapEntity: process.env.REACT_APP_API_ONTOLOGY_MAP_ENTITY || '/api/v1/ontology/{ontology}/map-entity',
  prefixMapEntity: process.env.REACT_APP_API_ONTOLOGY_PREFIX_MAP_ENTITY || '/api/v1/ontology/{prefix}/map-entity',
  ap239DataDictionary: process.env.REACT_APP_API_ONTOLOGY_AP239_DATA_DICTIONARY || '/api/v1/ontology/ap239/data-dictionary',
  ap239Mappings: process.env.REACT_APP_API_ONTOLOGY_AP239_MAPPINGS || '/api/v1/ontology/ap239/mappings/{source_format}',
  ap239MapEntity: process.env.REACT_APP_API_ONTOLOGY_AP239_MAP_ENTITY || '/api/v1/ontology/ap239/map-entity',
  ap239DomainPipelines: process.env.REACT_APP_API_ONTOLOGY_AP239_DOMAIN_PIPELINES || '/api/v1/ontology/ap239/domain-pipelines',
  ap242DataDictionary: process.env.REACT_APP_API_ONTOLOGY_AP242_DATA_DICTIONARY || '/api/v1/ontology/ap242/data-dictionary',
  ap242Mappings: process.env.REACT_APP_API_ONTOLOGY_AP242_MAPPINGS || '/api/v1/ontology/ap242/mappings/{source_format}',
  pipelineDomains: process.env.REACT_APP_API_ONTOLOGY_PIPELINE_DOMAINS || '/api/v1/ontology/pipelines/domains',
  pipelineDomain: process.env.REACT_APP_API_ONTOLOGY_PIPELINE_DOMAIN || '/api/v1/ontology/pipelines/domain/{domain_name}',
  pipelineProcess: process.env.REACT_APP_API_ONTOLOGY_PIPELINE_PROCESS || '/api/v1/ontology/pipelines/process',
  extract3dxml: process.env.REACT_APP_API_ONTOLOGY_EXTRACT_3DXML || '/api/v1/ontology/extract-3dxml',
  threeDxmlStatus: process.env.REACT_APP_API_ONTOLOGY_3DXML_STATUS || '/api/v1/ontology/3dxml/status/{task_id}',
  threeDxmlFormats: process.env.REACT_APP_API_ONTOLOGY_3DXML_FORMATS || '/api/v1/ontology/3dxml/formats',
  alignmentOptions: process.env.REACT_APP_API_ONTOLOGY_ALIGNMENT_OPTIONS || '/ontology-mappings',
  merge: process.env.REACT_APP_API_ONTOLOGY_MERGE || '/api/v1/ontology/merge',
  cleanupOldXsd: process.env.REACT_APP_API_ONTOLOGY_CLEANUP_OLD_XSD || '/api/v1/ontology/cleanup-old-xsd',
  exportRegistered: process.env.REACT_APP_API_ONTOLOGY_EXPORT || '/api/v1/ontology/{ontology}/export',
};

/**
 * Data Import Endpoints (v1)
 */
const IMPORT_ENDPOINTS = {
  upload: process.env.REACT_APP_API_IMPORT_UPLOAD || '/api/v1/import/upload',
  status: process.env.REACT_APP_API_IMPORT_STATUS || '/api/v1/import/status/{task_id}',
  preview: process.env.REACT_APP_API_IMPORT_PREVIEW || '/api/v1/import/preview/{task_id}',
  commit: process.env.REACT_APP_API_IMPORT_COMMIT || '/api/v1/import/commit/{task_id}',
  preCommit: process.env.REACT_APP_API_IMPORT_PRE_COMMIT || '/api/v1/import/pre-commit/{task_id}',
  cancel: process.env.REACT_APP_API_IMPORT_CANCEL || '/api/v1/import/cancel/{task_id}',
  owl: process.env.REACT_APP_API_IMPORT_OWL || '/api/v1/import/owl/{task_id}',
  owlExport: process.env.REACT_APP_API_IMPORT_OWL_EXPORT || '/api/v1/import/owl/{task_id}/export',
  artifacts: process.env.REACT_APP_API_IMPORT_ARTIFACTS || '/api/v1/import/artifacts/{task_id}',
  formats: process.env.REACT_APP_API_IMPORT_FORMATS || '/api/v1/import/formats',
  ollamaQuery: process.env.REACT_APP_API_IMPORT_OLLAMA_QUERY || '/api/v1/import/ollama/query',
  ollamaHealth: process.env.REACT_APP_API_IMPORT_OLLAMA_HEALTH || '/api/v1/import/ollama/health',
  tasks: process.env.REACT_APP_API_IMPORT_TASKS || '/api/v1/import/tasks',
  uploadDataImport: process.env.REACT_APP_API_DATA_IMPORT_UPLOAD || '/data-import/upload',
  statusDataImport: process.env.REACT_APP_API_DATA_IMPORT_STATUS || '/data-import/status/{task_id}',
  previewDataImport: process.env.REACT_APP_API_DATA_IMPORT_PREVIEW || '/data-import/preview/{task_id}',
  preCommitDataImport: process.env.REACT_APP_API_DATA_IMPORT_PRE_COMMIT || '/data-import/pre-commit/{task_id}',
  commitDataImport: process.env.REACT_APP_API_DATA_IMPORT_COMMIT || '/data-import/commit/{task_id}',
  cancelDataImport: process.env.REACT_APP_API_DATA_IMPORT_CANCEL || '/data-import/cancel/{task_id}',
  tasksDataImport: process.env.REACT_APP_API_DATA_IMPORT_TASKS || '/data-import/tasks',
};

const WORKFLOW_ENDPOINTS = {
  options: process.env.REACT_APP_API_WORKFLOW_OPTIONS || '/api/v1/workflows/options',
  execute: process.env.REACT_APP_API_WORKFLOW_EXECUTE || '/api/v1/workflows/execute',
  artifactFile: process.env.REACT_APP_API_WORKFLOW_ARTIFACT_FILE || '/api/v1/workflows/artifacts/{task_id}/{artifact_path}',
};

/**
 * Ingestion Endpoints (v1)
 */
const INGESTION_ENDPOINTS = {
  ingestData: process.env.REACT_APP_API_INGEST_DATA || '/api/v1/ingest-data',
  ingestDataRoot: process.env.REACT_APP_API_INGEST_DATA_ROOT || '/api/v1/ingest-data',
};

/**
 * Document/File Endpoints
 */
const DOCUMENT_ENDPOINTS = {
  formats: process.env.REACT_APP_API_DOCUMENTS_FORMATS || '/api/v1/documents/supported-formats',
  upload: process.env.REACT_APP_API_DOCUMENTS_UPLOAD || '/api/v1/documents/upload',
  uploadSingle: process.env.REACT_APP_API_DOCUMENTS_UPLOAD_SINGLE || '/api/v1/documents/upload-single',
  health: process.env.REACT_APP_API_DOCUMENTS_HEALTH || '/api/v1/documents/health',
};

/**
 * Admin Endpoints (v1)
 */
const ADMIN_ENDPOINTS = {
  health: process.env.REACT_APP_API_ADMIN_HEALTH || '/api/v1/admin/health',
  registry: process.env.REACT_APP_API_ADMIN_REGISTRY || '/api/v1/admin/registry',
  cleanSchema: process.env.REACT_APP_API_ADMIN_CLEAN_SCHEMA || '/api/v1/admin/clean-schema',
  clearCache: process.env.REACT_APP_API_ADMIN_CLEAR_CACHE || '/api/v1/admin/clear-cache',
  deleteData: process.env.REACT_APP_API_ADMIN_DELETE_DATA || '/api/v1/admin/delete-data',
  schemaStats: process.env.REACT_APP_API_ADMIN_SCHEMA_STATS || '/api/v1/admin/schema-stats',
  resetDatabase: process.env.REACT_APP_API_ADMIN_RESET_DATABASE || '/api/v1/admin/reset-database',
};

/**
 * Recommendation Endpoints
 */
const RECOMMENDATION_ENDPOINTS = {
  changeImpact: process.env.REACT_APP_API_RECOMMENDATIONS_CHANGE_IMPACT || '/recommendations/change-impact',
  similarParts: process.env.REACT_APP_API_RECOMMENDATIONS_SIMILAR_PARTS || '/recommendations/similar-parts',
  manufacturing: process.env.REACT_APP_API_RECOMMENDATIONS_MANUFACTURING || '/recommendations/manufacturing',
  health: process.env.REACT_APP_API_RECOMMENDATIONS_HEALTH || '/recommendations/health',
};


/**
 * Normalized Requirements Endpoints
 */
const REQUIREMENTS_ENDPOINTS = {
  list: process.env.REACT_APP_API_REQUIREMENTS_LIST || '/api/v1/requirements',
};

/**
 * Ontology Mapper Endpoints
 */
const ONTOLOGY_MAPPER_ENDPOINTS = {
  options: process.env.REACT_APP_API_ONTOLOGY_MAPPER_OPTIONS || '/ontology-mapper/options',
  mappings: process.env.REACT_APP_API_ONTOLOGY_MAPPER_MAPPINGS || '/ontology-mapper/{mapping_type}/mappings',
  dataDictionary: process.env.REACT_APP_API_ONTOLOGY_MAPPER_DATA_DICTIONARY || '/ontology-mapper/{mapping_type}/data-dictionary',
  vocabulary: process.env.REACT_APP_API_ONTOLOGY_MAPPER_VOCABULARY || '/ontology-mapper/{mapping_type}/vocabulary',
  stats: process.env.REACT_APP_API_ONTOLOGY_MAPPER_STATS || '/ontology-mapper/{mapping_type}/stats',
};


/**
 * Ontology Modeling Workbench Endpoints
 */
const MODELING_ENDPOINTS = {
  metamodel: process.env.REACT_APP_API_MODELING_METAMODEL || '/api/v1/modeling/metamodel',
  indexes: process.env.REACT_APP_API_MODELING_INDEXES || '/api/v1/modeling/indexes',
  graph: process.env.REACT_APP_API_MODELING_GRAPH || '/api/v1/modeling/graph',
  tree: process.env.REACT_APP_API_MODELING_TREE || '/api/v1/modeling/tree',
  search: process.env.REACT_APP_API_MODELING_SEARCH || '/api/v1/modeling/search',
  context: process.env.REACT_APP_API_MODELING_CONTEXT || '/api/v1/modeling/context/{element_id}',
  nodes: process.env.REACT_APP_API_MODELING_NODES || '/api/v1/modeling/nodes',
  node: process.env.REACT_APP_API_MODELING_NODE || '/api/v1/modeling/nodes/{element_id}',
  links: process.env.REACT_APP_API_MODELING_LINKS || '/api/v1/modeling/links',
  link: process.env.REACT_APP_API_MODELING_LINK || '/api/v1/modeling/links/{element_id}',
  validation: process.env.REACT_APP_API_MODELING_VALIDATION || '/api/v1/modeling/validation',
  seed: process.env.REACT_APP_API_MODELING_SEED || '/api/v1/modeling/seed',
  agentProposals: process.env.REACT_APP_API_MODELING_AGENT_PROPOSALS || '/api/v1/modeling/agent/proposals',
  agentProposalApprove: process.env.REACT_APP_API_MODELING_AGENT_PROPOSAL_APPROVE || '/api/v1/modeling/agent/proposals/{proposal_id}/approve',
  agentProposalReject: process.env.REACT_APP_API_MODELING_AGENT_PROPOSAL_REJECT || '/api/v1/modeling/agent/proposals/{proposal_id}/reject',
};

/**
 * Integration/Webhook Endpoints
 */
const INTEGRATION_ENDPOINTS = {
  embeddingsBuild: process.env.REACT_APP_API_EMBEDDINGS_BUILD || '/embeddings/build',
  neo4jWebhookV1: process.env.REACT_APP_API_WEBHOOKS_NEO4J_V1 || '/api/v1/webhooks/neo4j',
};

/** Optional ontology-agentic service endpoints. */
const AGENTIC_ENDPOINTS = {
  health: process.env.REACT_APP_AGENTIC_HEALTH || '/health',
  agents: process.env.REACT_APP_AGENTIC_AGENTS || '/api/v1/agents',
  runAgent: process.env.REACT_APP_AGENTIC_RUN_AGENT || '/api/v1/agents/{agent_name}/run',
  runWorkflow: process.env.REACT_APP_AGENTIC_RUN_WORKFLOW || '/api/v1/workflows/run',
};

/**
 * UI Configuration
 */
const UI_CONFIG = {
  graphMaxNodes: parseInt(process.env.REACT_APP_GRAPH_MAX_NODES || '2000', 10),
  graphAnimationEnabled: process.env.REACT_APP_GRAPH_ANIMATION_ENABLED !== 'false',
  autoLoadGraph: process.env.REACT_APP_AUTO_LOAD_GRAPH !== 'false',
};

/**
 * Utility function to build full URL from base and endpoint
 */
export const buildUrl = (endpoint) => {
  if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
    return endpoint;
  }
  return `${config.backendUrl}${endpoint}`;
};

/**
 * Utility function to replace path parameters in endpoints
 * Example: replaceParams('/api/v1/ontology/{ontology}', { ontology: 'ap239' })
 */
export const replaceParams = (endpoint, params) => {
  let result = endpoint;
  if (params) {
    Object.keys(params).forEach((key) => {
      result = result.replace(`{${key}}`, params[key]);
    });
  }
  return result;
};

/**
 * Export all API endpoints organized by category
 */
export const API = {
  health: HEALTH_ENDPOINTS,
  graph: GRAPH_ENDPOINTS,
  schema: SCHEMA_ENDPOINTS,
  chat: CHAT_ENDPOINTS,
  ontology: ONTOLOGY_ENDPOINTS,
  import: IMPORT_ENDPOINTS,
  workflow: WORKFLOW_ENDPOINTS,
  ingestion: INGESTION_ENDPOINTS,
  document: DOCUMENT_ENDPOINTS,
  admin: ADMIN_ENDPOINTS,
  recommendations: RECOMMENDATION_ENDPOINTS,
  requirements: REQUIREMENTS_ENDPOINTS,
  ontologyMapper: ONTOLOGY_MAPPER_ENDPOINTS,
  modeling: MODELING_ENDPOINTS,
  integration: INTEGRATION_ENDPOINTS,
  agentic: AGENTIC_ENDPOINTS,
  ui: UI_CONFIG,
};

// Log configuration in development
if (baseConfig.debug) {
  // eslint-disable-next-line no-console
  console.info('[CONFIG] API Configuration Loaded:', {
    environment: baseConfig.environment,
    backendUrl: baseConfig.backendUrl,
    agenticServiceUrl: baseConfig.agenticServiceUrl || '(not configured)',
    apiVersion: baseConfig.apiVersion,
    debug: baseConfig.debug,
    endpoints: {
      graph: GRAPH_ENDPOINTS,
      ontology: ONTOLOGY_ENDPOINTS,
      import: IMPORT_ENDPOINTS,
    },
  });
}

// Validate required configuration
if (!configuredBackendUrl && baseConfig.environment !== 'test') {
  // eslint-disable-next-line no-console
  console.warn('[CONFIG] Missing REACT_APP_BACKEND_URL. Using browser host with backend port 8000.');
}

export default config;
export { config, baseConfig };
