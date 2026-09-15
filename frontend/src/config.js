/**
 * API Configuration - Centralized endpoint mapping
 * All backend API endpoints are configured here via environment variables
 * This allows easy switching between environments without code changes
 */

// `import.meta.env` is Vite's supported browser-safe configuration surface.
// Keep the process fallback for Vitest and any remaining CRA-compatible test
// harnesses; it must not be the primary runtime source in the browser.
const viteEnv = import.meta.env || {};
const processEnv = typeof process !== 'undefined' && process.env ? process.env : {};
const setting = (name) => {
  const viteValues = [viteEnv[`VITE_${name}`], viteEnv[`REACT_APP_${name}`]];
  const processValues = [processEnv[`VITE_${name}`], processEnv[`REACT_APP_${name}`]];
  // Vitest stubs process.env at runtime; production Vite configuration is
  // compiled into import.meta.env and takes precedence in the browser.
  const values = viteEnv.MODE === 'test' ? [...processValues, ...viteValues] : [...viteValues, ...processValues];
  return values.find((value) => value !== undefined && value !== '') || '';
};
const configuredBackendUrl = setting('BACKEND_URL');
const configuredGatewayUrl = setting('API_GATEWAY_URL');
const configuredAgenticServiceUrl = setting('AGENTIC_SERVICE_URL');
const agenticEnabled = String(setting('AGENTIC_ENABLED')).trim().toLowerCase() === 'true';
const rewriteLocalhostBackend =
  String(setting('REWRITE_LOCALHOST_BACKEND')).trim().toLowerCase() === 'true';

const resolveLocalServiceUrl = (configuredUrl, fallbackPort) => {
  if (!configuredUrl) return '';
  try {
    const configured = new URL(configuredUrl);
    const browserHost = typeof window !== 'undefined' ? window.location?.hostname : '';
    const isLocalConfigured = configured.hostname === 'localhost' || configured.hostname === '127.0.0.1';
    const isRemoteBrowser = browserHost && browserHost !== 'localhost' && browserHost !== '127.0.0.1';
    if (isLocalConfigured && isRemoteBrowser) {
      configured.hostname = browserHost;
      if (!configured.port) configured.port = String(fallbackPort);
      return configured.toString().replace(/\/$/, '');
    }
  } catch (_err) {
    return configuredUrl.replace(/\/$/, '');
  }
  return configuredUrl.replace(/\/$/, '');
};

const resolveBackendUrl = () => {
  // The standalone deployment has no aggregate service.  Keep an accidental
  // unowned request same-origin rather than silently targeting retired :8000.
  const fallback = '';
  if (!configuredBackendUrl) return fallback;

  try {
    const configured = new URL(configuredBackendUrl);
    // Port 8000 belonged to the retired aggregate application. Existing local
    // .env files may still contain it, so never let it override the explicit
    // service topology or generate opaque connection-refused browser errors.
    if ((configured.hostname === 'localhost' || configured.hostname === '127.0.0.1') && configured.port === '8000') {
      return fallback;
    }
    const browserHost = typeof window !== 'undefined' ? window.location?.hostname : '';
    const isLocalConfigured = configured.hostname === 'localhost' || configured.hostname === '127.0.0.1';
    const isRemoteBrowser = browserHost && browserHost !== 'localhost' && browserHost !== '127.0.0.1';
    if (rewriteLocalhostBackend && isLocalConfigured && isRemoteBrowser) {
      configured.hostname = browserHost;
      return configured.toString().replace(/\/$/, '');
    }
    if (isLocalConfigured && browserHost && (browserHost === 'localhost' || browserHost === '127.0.0.1')) {
      configured.hostname = browserHost;
      return configured.toString().replace(/\/$/, '');
    }
  } catch (_err) {
    return fallback;
  }

  return configuredBackendUrl.replace(/\/$/, '');
};

// Base configuration
const baseConfig = {
  backendUrl: resolveBackendUrl(),
  agenticEnabled,
  agenticServiceUrl: agenticEnabled
    ? resolveLocalServiceUrl(configuredAgenticServiceUrl, 8012)
    : '',
  apiVersion: setting('API_VERSION') || 'v1',
  environment: setting('ENV') || 'development',
  debug: setting('DEBUG') === 'true',
  logLevel: setting('LOG_LEVEL') || 'info',
  requestTimeout: parseInt(setting('REQUEST_TIMEOUT') || '300000', 10),
  chatStreamTimeout: parseInt(setting('CHAT_STREAM_TIMEOUT') || '900000', 10),
  // This key is intentionally opt-in. It is visible to browser users and is
  // appropriate only for a trusted internal admin deployment.
  adminApiKey: setting('ADMIN_API_KEY'),
  // Optional only for trusted internal/token deployments. Never commit this
  // value; production Entra deployments should leave it empty.
  apiToken: setting('API_TOKEN'),
  apiActor: setting('API_ACTOR') || 'ui-user',
};

const gatewayUrl = configuredGatewayUrl ? configuredGatewayUrl.replace(/\/$/, '') : '';
const browserHost = typeof window !== 'undefined' && window.location?.hostname
  ? window.location.hostname
  : '127.0.0.1';
const localServiceUrl = (port) => `http://${browserHost}:${port}`;
const configuredServiceUrl = (name, port, gatewayPath) => (
  setting(`${name.toUpperCase()}_SERVICE_URL`) || (gatewayUrl ? `${gatewayUrl}${gatewayPath}` : localServiceUrl(port))
).replace(/\/$/, '');

// Service ownership is explicit.  An API gateway can replace these URLs as a
// single deployment concern; direct developer mode talks to the same service
// contracts on their local ports.
const semanticServiceUrls = Object.freeze({
  qif: configuredServiceUrl('qif', 8010, '/qif'),
  ontology: configuredServiceUrl('ontology', 8011, '/ontology'),
  agentic: configuredServiceUrl('agentic', 8012, '/agentic'),
  graph: configuredServiceUrl('graph', 8013, '/graph'),
  ingestion: configuredServiceUrl('ingestion', 8014, '/ingestion'),
  oslc: configuredServiceUrl('oslc', 8015, '/oslc'),
  catalog: configuredServiceUrl('catalog', 8016, '/catalog'),
  dataProducts: configuredServiceUrl('data_product', 8017, '/data-products'),
  dataPipeline: configuredServiceUrl('data_pipeline', 8019, '/data-pipeline'),
});

/** Build a URL for new standalone-service features during monolith migration. */
export const buildSemanticServiceUrl = (service, path = '') => {
  const baseUrl = semanticServiceUrls[service];
  if (!baseUrl) throw new Error(`Semantic service '${service}' is not configured`);
  return `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
};

const SERVICE_PATHS = [
  ['qif', /^\/api\/v1\/qif(?:\/|$)/],
  ['ontology', /^\/api\/v1\/ontologies(?:\/|$)/],
  ['ontology', /^\/api\/v1\/modeling(?:\/|$)/],
  ['ontology', /^\/api\/v1\/admin(?:\/|$)/],
  ['ontology', /^\/api\/v1\/metadata-registry(?:\/|$)/],
  // Retained ingestion-owned artifact registry.  Keep these narrow routes
  // ahead of the semantic workbench compatibility namespace below.
  ['ingestion', /^\/api\/v1\/ontology\/(?:upload|registered|merge|cleanup-old-xsd)(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/ontology\/[^/]+\/(?:taxonomy|reason|inference\/preview|export)(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/ontology\/[^/]+$/],
  // The workbench contract is owned by the ontology service. XSD/XML source
  // profiles remain under ingestion; this namespace is semantic workbench only.
  ['ontology', /^\/api\/v1\/ontology(?:\/|$)/],
  ['graph', /^\/api\/v1\/graph(?:\/|$)/],
  ['graph', /^\/api\/v1\/requirements(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/(?:ingestion|ingest-data|ap242|schema-conversions|source-profiles|engineering-workflows)(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/import(?:\/|$)/],
  ['oslc', /^(?:\/api\/v1\/oslc|\/oslc)(?:\/|$)/],
  ['catalog', /^\/api\/v1\/catalog\/products(?:\/|$)/],
  ['dataProducts', /^\/api\/v1\/data-products(?:\/|$)/],
  ['dataPipeline', /^\/api\/v1\/pipeline(?:\/|$)/],
  ['agentic', /^\/api\/v1\/(?:agents|tools|mcp-servers|workflows|plans|runs|workflow-runs|catalog\/validate|chat)(?:\/|$)/],
  ['agentic', /^\/api\/v1\/code-audit(?:\/|$)/],
  ['graph', /^\/recommendations(?:\/|$)/],
];

export const getServiceForPath = (endpoint = '') => {
  if (typeof endpoint !== 'string' || !endpoint.startsWith('/')) return null;
  return SERVICE_PATHS.find(([, pattern]) => pattern.test(endpoint))?.[0] || null;
};

// Deprecated: Keep old property for backward compatibility
const config = {
  ...baseConfig,
  apiUrl: baseConfig.backendUrl,
  gatewayUrl,
  semanticServiceUrls,
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
  // Knowledge Companion belongs to the agentic control plane.  Keeping its
  // contract under /api/v1 prevents the SPA from reviving the retired :8000 API.
  chat: process.env.REACT_APP_API_CHAT || '/api/v1/chat',
  chatStream: process.env.REACT_APP_API_CHAT_STREAM || '/api/v1/chat-stream',
  validate: process.env.REACT_APP_API_CHAT_VALIDATE || '/api/v1/chat/validate',
  jobs: process.env.REACT_APP_API_CHAT_JOBS || '/api/v1/chat/jobs',
  jobStatus: process.env.REACT_APP_API_CHAT_JOB_STATUS || '/api/v1/chat/jobs/{job_id}',
  health: process.env.REACT_APP_API_CHAT_HEALTH || '/api/v1/chat/health',
  status: process.env.REACT_APP_API_CHAT_STATUS || '/api/v1/chat/status',
  capabilities: process.env.REACT_APP_API_CHAT_CAPABILITIES || '/api/v1/chat/capabilities',
  sampleQueries: process.env.REACT_APP_API_CHAT_SAMPLE_QUERIES || '/api/v1/chat/sample-queries',
};

/**
 * Ontology Management Endpoints (v1)
 */
const ONTOLOGY_ENDPOINTS = {
  upload: process.env.REACT_APP_API_ONTOLOGY_UPLOAD || '/api/v1/ontology/upload',
  registered: process.env.REACT_APP_API_ONTOLOGY_REGISTERED || '/api/v1/ontology/registered',
  get: process.env.REACT_APP_API_ONTOLOGY_GET || '/api/v1/ontology/{ontology}',
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
  governed: process.env.REACT_APP_API_GOVERNED_IMPORT || '/api/v1/governed-import',
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
  jobs: process.env.REACT_APP_API_DOCUMENTS_JOBS || '/api/v1/documents/jobs',
  job: process.env.REACT_APP_API_DOCUMENTS_JOB || '/api/v1/documents/jobs/{task_id}',
  cancelJob: process.env.REACT_APP_API_DOCUMENTS_CANCEL_JOB || '/api/v1/documents/jobs/{task_id}/cancel',
  jobArtifacts: process.env.REACT_APP_API_DOCUMENTS_JOB_ARTIFACTS || '/api/v1/documents/jobs/{task_id}/artifacts',
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

const METADATA_REGISTRY_ENDPOINTS = {
  assets: process.env.REACT_APP_API_METADATA_REGISTRY_ASSETS || '/api/v1/metadata-registry/assets',
  asset: process.env.REACT_APP_API_METADATA_REGISTRY_ASSET || '/api/v1/metadata-registry/assets/{asset_id}',
  transition: process.env.REACT_APP_API_METADATA_REGISTRY_TRANSITION || '/api/v1/metadata-registry/assets/{asset_id}/transition',
  history: process.env.REACT_APP_API_METADATA_REGISTRY_HISTORY || '/api/v1/metadata-registry/assets/{asset_id}/history',
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

const REPORT_ENDPOINTS = {
  xsdRelational: process.env.REACT_APP_API_REPORT_XSD_RELATIONAL || '/api/v1/reports/xsd-relational',
};

const QIF_ENDPOINTS = {
  catalog: process.env.REACT_APP_API_QIF_CATALOG || '/api/v1/qif/catalog',
  health: process.env.REACT_APP_API_QIF_HEALTH || '/api/v1/qif/health',
  agents: process.env.REACT_APP_API_QIF_AGENTS || '/api/v1/qif/agents',
  startReferenceTask: process.env.REACT_APP_API_QIF_START_REFERENCE || '/api/v1/qif/tasks/reference',
  startUploadTask: process.env.REACT_APP_API_QIF_START_UPLOAD || '/api/v1/qif/tasks/upload',
  tasks: process.env.REACT_APP_API_QIF_TASKS || '/api/v1/qif/tasks',
  task: process.env.REACT_APP_API_QIF_TASK || '/api/v1/qif/tasks/{task_id}',
  preview: process.env.REACT_APP_API_QIF_PREVIEW || '/api/v1/qif/tasks/{task_id}/preview',
  artifact: process.env.REACT_APP_API_QIF_ARTIFACT || '/api/v1/qif/tasks/{task_id}/artifacts/{artifact_path}',
  commit: process.env.REACT_APP_API_QIF_COMMIT || '/api/v1/qif/tasks/{task_id}/commit',
  cancel: process.env.REACT_APP_API_QIF_CANCEL || '/api/v1/qif/tasks/{task_id}/cancel',
  retryGraph: process.env.REACT_APP_API_QIF_RETRY_GRAPH || '/api/v1/qif/tasks/{task_id}/retry-graph',
};

/** Optional ontology-agentic service endpoints. */
const AGENTIC_ENDPOINTS = {
  health: process.env.REACT_APP_AGENTIC_HEALTH || '/health',
  agents: process.env.REACT_APP_AGENTIC_AGENTS || '/api/v1/agents',
  tools: process.env.REACT_APP_AGENTIC_TOOLS || '/api/v1/tools',
  openApiImport: process.env.REACT_APP_AGENTIC_OPENAPI_IMPORT || '/api/v1/openapi/import',
  runAgent: process.env.REACT_APP_AGENTIC_RUN_AGENT || '/api/v1/agents/{agent_name}/run',
  runWorkflow: process.env.REACT_APP_AGENTIC_RUN_WORKFLOW || '/api/v1/workflows/run',
};

/**
 * UI Configuration
 */
const UI_CONFIG = {
  graphMaxNodes: parseInt(process.env.REACT_APP_GRAPH_MAX_NODES || '750', 10),
  graphAnimationEnabled: process.env.REACT_APP_GRAPH_ANIMATION_ENABLED !== 'false',
  autoLoadGraph: process.env.REACT_APP_AUTO_LOAD_GRAPH !== 'false',
};

/**
 * Utility function to build full URL from base and endpoint
 */
export const buildUrl = (endpoint) => {
  if (!endpoint || typeof endpoint !== 'string') {
    return '';
  }
  if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
    return endpoint;
  }
  const service = getServiceForPath(endpoint);
  if (service) return buildSemanticServiceUrl(service, endpoint);
  return `${config.backendUrl}${endpoint}`;
};

/**
 * Utility function to replace path parameters in endpoints
 * Example: replaceParams('/api/v1/ontology/{ontology}', { ontology: 'ap239' })
 */
export const replaceParams = (endpoint, params, options = {}) => {
  let result = endpoint;
  if (params) {
    Object.keys(params).forEach((key) => {
      const value = String(params[key] ?? '');
      const replacement = options.pathParams?.includes(key)
        ? value.split('/').map(encodeURIComponent).join('/')
        : encodeURIComponent(value);
      result = result.split(`{${key}}`).join(replacement);
    });
  }
  return result;
};

/**
 * Export all API endpoints organized by category
 */
export const API = {
  health: HEALTH_ENDPOINTS,
  schema: SCHEMA_ENDPOINTS,
  chat: CHAT_ENDPOINTS,
  ontology: ONTOLOGY_ENDPOINTS,
  import: IMPORT_ENDPOINTS,
  workflow: WORKFLOW_ENDPOINTS,
  ingestion: INGESTION_ENDPOINTS,
  document: DOCUMENT_ENDPOINTS,
  admin: ADMIN_ENDPOINTS,
  metadataRegistry: METADATA_REGISTRY_ENDPOINTS,
  recommendations: RECOMMENDATION_ENDPOINTS,
  reports: REPORT_ENDPOINTS,
  qif: QIF_ENDPOINTS,
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
    agenticEnabled: baseConfig.agenticEnabled,
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
const isTestRuntime = viteEnv.MODE === 'test' || processEnv.NODE_ENV === 'test';
if (!configuredBackendUrl && baseConfig.environment !== 'test' && !isTestRuntime) {
  // eslint-disable-next-line no-console
  console.warn('[CONFIG] Missing BACKEND_URL. Explicit standalone-service routes remain available; unowned legacy routes are disabled.');
}

export default config;
export { config, baseConfig };
