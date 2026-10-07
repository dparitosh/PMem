import { serviceForContractPath } from './services/serviceContractRegistry';
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
  const runtime = typeof window !== 'undefined' ? window.DEPO_RUNTIME_CONFIG : null;
  if (runtime && Object.prototype.hasOwnProperty.call(runtime, `VITE_${name}`)) {
    return runtime[`VITE_${name}`];
  }
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
  ceim: configuredServiceUrl('ceim', 8018, '/ceim'),
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
  ['ceim', /^\/api\/v1\/ceim(?:\/|$)/],
  // Retained ingestion-owned artifact registry.  Keep these narrow routes
  // ahead of the semantic workbench compatibility namespace below.
  ['ingestion', /^\/api\/v1\/ontology\/(?:upload|registered|merge|cleanup-old-xsd)(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/ontology\/[^/]+\/(?:taxonomy|reason|inference\/preview|export|data-dictionary)(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/ontology\/[^/]+$/],
  // The workbench contract is owned by the ontology service. XSD/XML source
  // profiles remain under ingestion; this namespace is semantic workbench only.
  ['ontology', /^\/api\/v1\/ontology(?:\/|$)/],
  ['graph', /^\/api\/v1\/graph(?:\/|$)/],
  ['graph', /^\/api\/v1\/(?:graphql|sparql)(?:\/|$)/],
  ['graph', /^\/api\/v1\/requirements(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/(?:ingestion|ingest-data|ap242|schema-conversions|source-profiles|engineering-workflows|governed-import|sysml-v2)(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/import(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/documents(?:\/|$)/],
  ['ingestion', /^\/api\/v1\/reports(?:\/|$)/],
  ['oslc', /^(?:\/api\/v1\/oslc|\/oslc)(?:\/|$)/],
  ['catalog', /^\/api\/v1\/catalog\/(?:products|artifacts)(?:\/|$)/],
  ['dataProducts', /^\/api\/v1\/data-products(?:\/|$)/],
  ['dataPipeline', /^\/api\/v1\/pipeline(?:\/|$)/],
  ['agentic', /^\/api\/v1\/(?:agents|tools|mcp-servers|workflows|plans|runs|workflow-runs|observability|metrics|catalog\/validate|chat|chat-stream|ontology-agents)(?:\/|$)/],
  ['agentic', /^\/api\/v1\/code-audit(?:\/|$)/],
  ['agentic', /^\/api\/v1\/llm(?:\/|$)/],
  ['graph', /^\/recommendations(?:\/|$)/],
];

export const getServiceForPath = (endpoint = '', method) => {
  if (typeof endpoint !== 'string' || !endpoint.startsWith('/')) return null;
  return serviceForContractPath(endpoint.split('?')[0], method) || SERVICE_PATHS.find(([, pattern]) => pattern.test(endpoint))?.[0] || null;
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
  health: setting('API_HEALTH') || '/health',
  ready: setting('API_READY') || '/ready',
  graphMetrics: setting('API_GRAPH_METRICS') || '/graph-metrics',
  ontologiesAvailable: setting('API_ONTOLOGIES_AVAILABLE') || '/ontologies/available',
  neo4jHealth: setting('API_NEO4J_HEALTH') || '/health/neo4j',
};

/**
 * Schema & Metadata Endpoints
 */
const SCHEMA_ENDPOINTS = {
  // The retired aggregate backend owned /schema. Standalone deployments have
  // no equivalent route, so fetch it only when an operator explicitly maps it.
  schema: setting('API_SCHEMA'),
  ap242RotorPmi: setting('API_AP242_ROTOR_PMI') || '/ap242/rotor-shaft-pmi',
  ap242Search: setting('API_AP242_SEARCH') || '/ap242/search',
  reports: setting('API_REPORTS') || '/reports',
};

/**
 * Chat & Conversation Endpoints
 */
const CHAT_ENDPOINTS = {
  // Knowledge Companion belongs to the agentic control plane.  Keeping its
  // contract under /api/v1 prevents the SPA from reviving the retired :8000 API.
  chat: setting('API_CHAT') || '/api/v1/chat',
  chatStream: setting('API_CHAT_STREAM') || '/api/v1/chat-stream',
  validate: setting('API_CHAT_VALIDATE') || '/api/v1/chat/validate',
  jobs: setting('API_CHAT_JOBS') || '/api/v1/chat/jobs',
  jobStatus: setting('API_CHAT_JOB_STATUS') || '/api/v1/chat/jobs/{job_id}',
  health: setting('API_CHAT_HEALTH') || '/api/v1/chat/health',
  status: setting('API_CHAT_STATUS') || '/api/v1/chat/status',
  capabilities: setting('API_CHAT_CAPABILITIES') || '/api/v1/chat/capabilities',
  sampleQueries: setting('API_CHAT_SAMPLE_QUERIES') || '/api/v1/chat/sample-queries',
};

/**
 * Ontology Management Endpoints (v1)
 */
const ONTOLOGY_ENDPOINTS = {
  upload: setting('API_ONTOLOGY_UPLOAD') || '/api/v1/ontology/upload',
  registered: setting('API_ONTOLOGY_REGISTERED') || '/api/v1/ontology/registered',
  get: setting('API_ONTOLOGY_GET') || '/api/v1/ontology/{ontology}',
  taxonomy: setting('API_ONTOLOGY_TAXONOMY') || '/api/v1/ontology/{ontology}/taxonomy',
  reason: setting('API_ONTOLOGY_REASON') || '/api/v1/ontology/{ontology}/reason',
  inferencePreview: setting('API_ONTOLOGY_INFERENCE_PREVIEW') || '/api/v1/ontology/{ontology}/inference/preview',
  skosValidate: setting('API_ONTOLOGY_SKOS_VALIDATE') || '/api/v1/ontology/semantic/skos/validate',
  skosSearch: setting('API_ONTOLOGY_SKOS_SEARCH') || '/api/v1/ontology/semantic/skos/search',
  skosTraverse: setting('API_ONTOLOGY_SKOS_TRAVERSE') || '/api/v1/ontology/semantic/skos/traverse',
  skosStoragePlan: setting('API_ONTOLOGY_SKOS_STORAGE_PLAN') || '/api/v1/ontology/semantic/skos/storage-plan',
  ruleValidate: setting('API_ONTOLOGY_RULE_VALIDATE') || '/api/v1/ontology/semantic/rules/validate',
  ruleExecutePreview: setting('API_ONTOLOGY_RULE_EXECUTE_PREVIEW') || '/api/v1/ontology/semantic/rules/execute-preview',
  ruleMaterializationPlan: setting('API_ONTOLOGY_RULE_MATERIALIZATION_PLAN') || '/api/v1/ontology/semantic/rules/materialization-plan',
  dataDictionary: setting('API_ONTOLOGY_DATA_DICTIONARY') || '/api/v1/ontology/{ontology}/data-dictionary',
  prefixDataDictionary: setting('API_ONTOLOGY_PREFIX_DATA_DICTIONARY') || '/api/v1/ontology/{prefix}/data-dictionary',
  mappings: setting('API_ONTOLOGY_MAPPINGS') || '/api/v1/ontology/{ontology}/mappings/{type}',
  prefixMappings: setting('API_ONTOLOGY_PREFIX_MAPPINGS') || '/api/v1/ontology/{prefix}/mappings/{source_format}',
  mapEntity: setting('API_ONTOLOGY_MAP_ENTITY') || '/api/v1/ontology/{ontology}/map-entity',
  prefixMapEntity: setting('API_ONTOLOGY_PREFIX_MAP_ENTITY') || '/api/v1/ontology/{prefix}/map-entity',
  ap239DataDictionary: setting('API_ONTOLOGY_AP239_DATA_DICTIONARY') || '/api/v1/ontology/ap239/data-dictionary',
  ap239Mappings: setting('API_ONTOLOGY_AP239_MAPPINGS') || '/api/v1/ontology/ap239/mappings/{source_format}',
  ap239MapEntity: setting('API_ONTOLOGY_AP239_MAP_ENTITY') || '/api/v1/ontology/ap239/map-entity',
  ap239DomainPipelines: setting('API_ONTOLOGY_AP239_DOMAIN_PIPELINES') || '/api/v1/ontology/ap239/domain-pipelines',
  ap242DataDictionary: setting('API_ONTOLOGY_AP242_DATA_DICTIONARY') || '/api/v1/ontology/ap242/data-dictionary',
  ap242Mappings: setting('API_ONTOLOGY_AP242_MAPPINGS') || '/api/v1/ontology/ap242/mappings/{source_format}',
  pipelineDomains: setting('API_ONTOLOGY_PIPELINE_DOMAINS') || '/api/v1/ontology/pipelines/domains',
  pipelineDomain: setting('API_ONTOLOGY_PIPELINE_DOMAIN') || '/api/v1/ontology/pipelines/domain/{domain_name}',
  pipelineProcess: setting('API_ONTOLOGY_PIPELINE_PROCESS') || '/api/v1/ontology/pipelines/process',
  extract3dxml: setting('API_ONTOLOGY_EXTRACT_3DXML') || '/api/v1/ontology/extract-3dxml',
  threeDxmlStatus: setting('API_ONTOLOGY_3DXML_STATUS') || '/api/v1/ontology/3dxml/status/{task_id}',
  threeDxmlFormats: setting('API_ONTOLOGY_3DXML_FORMATS') || '/api/v1/ontology/3dxml/formats',
  alignmentOptions: setting('API_ONTOLOGY_ALIGNMENT_OPTIONS') || '/ontology-mappings',
  merge: setting('API_ONTOLOGY_MERGE') || '/api/v1/ontology/merge',
  governedMergePreview: setting('API_ONTOLOGY_GOVERNED_MERGE_PREVIEW') || '/api/v1/ontologies/merges/preview',
  governedMergeApply: setting('API_ONTOLOGY_GOVERNED_MERGE_APPLY') || '/api/v1/ontologies/merges/{preview_id}/apply',
  cleanupOldXsd: setting('API_ONTOLOGY_CLEANUP_OLD_XSD') || '/api/v1/ontology/cleanup-old-xsd',
  exportRegistered: setting('API_ONTOLOGY_EXPORT') || '/api/v1/ontology/{ontology}/export',
};

/**
 * Data Import Endpoints (v1)
 */
const IMPORT_ENDPOINTS = {
  upload: setting('API_IMPORT_UPLOAD') || '/api/v1/import/upload',
  status: setting('API_IMPORT_STATUS') || '/api/v1/import/status/{task_id}',
  preview: setting('API_IMPORT_PREVIEW') || '/api/v1/import/preview/{task_id}',
  commit: setting('API_IMPORT_COMMIT') || '/api/v1/import/commit/{task_id}',
  preCommit: setting('API_IMPORT_PRE_COMMIT') || '/api/v1/import/pre-commit/{task_id}',
  cancel: setting('API_IMPORT_CANCEL') || '/api/v1/import/cancel/{task_id}',
  owl: setting('API_IMPORT_OWL') || '/api/v1/import/owl/{task_id}',
  owlExport: setting('API_IMPORT_OWL_EXPORT') || '/api/v1/import/owl/{task_id}/export',
  artifacts: setting('API_IMPORT_ARTIFACTS') || '/api/v1/import/artifacts/{task_id}',
  formats: setting('API_IMPORT_FORMATS') || '/api/v1/import/formats',
  tasks: setting('API_IMPORT_TASKS') || '/api/v1/import/tasks',
  governed: setting('API_GOVERNED_IMPORT') || '/api/v1/governed-import',
  uploadDataImport: setting('API_DATA_IMPORT_UPLOAD') || '/data-import/upload',
  statusDataImport: setting('API_DATA_IMPORT_STATUS') || '/data-import/status/{task_id}',
  previewDataImport: setting('API_DATA_IMPORT_PREVIEW') || '/data-import/preview/{task_id}',
  preCommitDataImport: setting('API_DATA_IMPORT_PRE_COMMIT') || '/data-import/pre-commit/{task_id}',
  commitDataImport: setting('API_DATA_IMPORT_COMMIT') || '/data-import/commit/{task_id}',
  cancelDataImport: setting('API_DATA_IMPORT_CANCEL') || '/data-import/cancel/{task_id}',
  tasksDataImport: setting('API_DATA_IMPORT_TASKS') || '/data-import/tasks',
};

const WORKFLOW_ENDPOINTS = {
  options: setting('API_WORKFLOW_OPTIONS') || '/api/v1/workflows/options',
  execute: setting('API_WORKFLOW_EXECUTE') || '/api/v1/workflows/execute',
  artifactFile: setting('API_WORKFLOW_ARTIFACT_FILE') || '/api/v1/workflows/artifacts/{task_id}/{artifact_path}',
};

/**
 * Ingestion Endpoints (v1)
 */
const INGESTION_ENDPOINTS = {
  ingestData: setting('API_INGEST_DATA') || '/api/v1/ingest-data',
  ingestDataRoot: setting('API_INGEST_DATA_ROOT') || '/api/v1/ingest-data',
};

/**
 * Document/File Endpoints
 */
const DOCUMENT_ENDPOINTS = {
  formats: setting('API_DOCUMENTS_FORMATS') || '/api/v1/documents/supported-formats',
  upload: setting('API_DOCUMENTS_UPLOAD') || '/api/v1/documents/upload',
  uploadSingle: setting('API_DOCUMENTS_UPLOAD_SINGLE') || '/api/v1/documents/upload-single',
  jobs: setting('API_DOCUMENTS_JOBS') || '/api/v1/documents/jobs',
  job: setting('API_DOCUMENTS_JOB') || '/api/v1/documents/jobs/{task_id}',
  cancelJob: setting('API_DOCUMENTS_CANCEL_JOB') || '/api/v1/documents/jobs/{task_id}/cancel',
  jobArtifacts: setting('API_DOCUMENTS_JOB_ARTIFACTS') || '/api/v1/documents/jobs/{task_id}/artifacts',
  health: setting('API_DOCUMENTS_HEALTH') || '/api/v1/documents/health',
};

/**
 * Admin Endpoints (v1)
 */
const ADMIN_ENDPOINTS = {
  health: setting('API_ADMIN_HEALTH') || '/api/v1/admin/health',
  registry: setting('API_ADMIN_REGISTRY') || '/api/v1/admin/registry',
  cleanSchema: setting('API_ADMIN_CLEAN_SCHEMA') || '/api/v1/admin/clean-schema',
  clearCache: setting('API_ADMIN_CLEAR_CACHE') || '/api/v1/admin/clear-cache',
  deleteData: setting('API_ADMIN_DELETE_DATA') || '/api/v1/admin/delete-data',
  schemaStats: setting('API_ADMIN_SCHEMA_STATS') || '/api/v1/admin/schema-stats',
  resetDatabase: setting('API_ADMIN_RESET_DATABASE') || '/api/v1/admin/reset-database',
};

const METADATA_REGISTRY_ENDPOINTS = {
  assets: setting('API_METADATA_REGISTRY_ASSETS') || '/api/v1/metadata-registry/assets',
  asset: setting('API_METADATA_REGISTRY_ASSET') || '/api/v1/metadata-registry/assets/{asset_id}',
  transition: setting('API_METADATA_REGISTRY_TRANSITION') || '/api/v1/metadata-registry/assets/{asset_id}/transition',
  history: setting('API_METADATA_REGISTRY_HISTORY') || '/api/v1/metadata-registry/assets/{asset_id}/history',
};

/**
 * Recommendation Endpoints
 */
const RECOMMENDATION_ENDPOINTS = {
  changeImpact: setting('API_RECOMMENDATIONS_CHANGE_IMPACT') || '/recommendations/change-impact',
  similarParts: setting('API_RECOMMENDATIONS_SIMILAR_PARTS') || '/recommendations/similar-parts',
  manufacturing: setting('API_RECOMMENDATIONS_MANUFACTURING') || '/recommendations/manufacturing',
  health: setting('API_RECOMMENDATIONS_HEALTH') || '/recommendations/health',
};


/**
 * Normalized Requirements Endpoints
 */
const REQUIREMENTS_ENDPOINTS = {
  list: setting('API_REQUIREMENTS_LIST') || '/api/v1/requirements',
};

/**
 * Ontology Mapper Endpoints
 */
const ONTOLOGY_MAPPER_ENDPOINTS = {
  options: setting('API_ONTOLOGY_MAPPER_OPTIONS') || '/ontology-mapper/options',
  mappings: setting('API_ONTOLOGY_MAPPER_MAPPINGS') || '/ontology-mapper/{mapping_type}/mappings',
  dataDictionary: setting('API_ONTOLOGY_MAPPER_DATA_DICTIONARY') || '/ontology-mapper/{mapping_type}/data-dictionary',
  vocabulary: setting('API_ONTOLOGY_MAPPER_VOCABULARY') || '/ontology-mapper/{mapping_type}/vocabulary',
  stats: setting('API_ONTOLOGY_MAPPER_STATS') || '/ontology-mapper/{mapping_type}/stats',
};


/**
 * Ontology Modeling Workbench Endpoints
 */
const MODELING_ENDPOINTS = {
  metamodel: setting('API_MODELING_METAMODEL') || '/api/v1/modeling/metamodel',
  indexes: setting('API_MODELING_INDEXES') || '/api/v1/modeling/indexes',
  graph: setting('API_MODELING_GRAPH') || '/api/v1/modeling/graph',
  tree: setting('API_MODELING_TREE') || '/api/v1/modeling/tree',
  search: setting('API_MODELING_SEARCH') || '/api/v1/modeling/search',
  context: setting('API_MODELING_CONTEXT') || '/api/v1/modeling/context/{element_id}',
  nodes: setting('API_MODELING_NODES') || '/api/v1/modeling/nodes',
  node: setting('API_MODELING_NODE') || '/api/v1/modeling/nodes/{element_id}',
  links: setting('API_MODELING_LINKS') || '/api/v1/modeling/links',
  link: setting('API_MODELING_LINK') || '/api/v1/modeling/links/{element_id}',
  validation: setting('API_MODELING_VALIDATION') || '/api/v1/modeling/validation',
  seed: setting('API_MODELING_SEED') || '/api/v1/modeling/seed',
  agentProposals: setting('API_MODELING_AGENT_PROPOSALS') || '/api/v1/modeling/agent/proposals',
  agentProposalApprove: setting('API_MODELING_AGENT_PROPOSAL_APPROVE') || '/api/v1/modeling/agent/proposals/{proposal_id}/approve',
  agentProposalReject: setting('API_MODELING_AGENT_PROPOSAL_REJECT') || '/api/v1/modeling/agent/proposals/{proposal_id}/reject',
};

/**
 * Integration/Webhook Endpoints
 */
const INTEGRATION_ENDPOINTS = {
  embeddingsBuild: setting('API_EMBEDDINGS_BUILD') || '/embeddings/build',
  neo4jWebhookV1: setting('API_WEBHOOKS_NEO4J_V1') || '/api/v1/webhooks/neo4j',
};

const REPORT_ENDPOINTS = {
  xsdRelational: setting('API_REPORT_XSD_RELATIONAL') || '/api/v1/reports/xsd-relational',
};

const QIF_ENDPOINTS = {
  catalog: setting('API_QIF_CATALOG') || '/api/v1/qif/catalog',
  health: setting('API_QIF_HEALTH') || '/api/v1/qif/health',
  agents: setting('API_QIF_AGENTS') || '/api/v1/qif/agents',
  startReferenceTask: setting('API_QIF_START_REFERENCE') || '/api/v1/qif/tasks/reference',
  startUploadTask: setting('API_QIF_START_UPLOAD') || '/api/v1/qif/tasks/upload',
  tasks: setting('API_QIF_TASKS') || '/api/v1/qif/tasks',
  task: setting('API_QIF_TASK') || '/api/v1/qif/tasks/{task_id}',
  preview: setting('API_QIF_PREVIEW') || '/api/v1/qif/tasks/{task_id}/preview',
  artifact: setting('API_QIF_ARTIFACT') || '/api/v1/qif/tasks/{task_id}/artifacts/{artifact_path}',
  commit: setting('API_QIF_COMMIT') || '/api/v1/qif/tasks/{task_id}/commit',
  cancel: setting('API_QIF_CANCEL') || '/api/v1/qif/tasks/{task_id}/cancel',
  retryGraph: setting('API_QIF_RETRY_GRAPH') || '/api/v1/qif/tasks/{task_id}/retry-graph',
};

/** Optional ontology-agentic service endpoints. */
const AGENTIC_ENDPOINTS = {
  health: setting('AGENTIC_HEALTH') || '/healthz',
  agents: setting('AGENTIC_AGENTS') || '/api/v1/agents',
  tools: setting('AGENTIC_TOOLS') || '/api/v1/tools',
  runAgent: setting('AGENTIC_RUN_AGENT') || '/api/v1/runs',
  runWorkflow: setting('AGENTIC_RUN_WORKFLOW') || '/api/v1/workflow-runs',
  orchestrateOntology: setting('AGENTIC_ONTOLOGY_ORCHESTRATE') || '/api/v1/ontology-agents/orchestrate',
  observabilitySummary: setting('AGENTIC_OBSERVABILITY_SUMMARY') || '/api/v1/observability/summary',
  observabilityRuns: setting('AGENTIC_OBSERVABILITY_RUNS') || '/api/v1/observability/runs',
};

/**
 * UI Configuration
 */
const UI_CONFIG = {
  graphMaxNodes: parseInt(setting('GRAPH_MAX_NODES') || '750', 10),
  graphAnimationEnabled: setting('GRAPH_ANIMATION_ENABLED') !== 'false',
  autoLoadGraph: setting('AUTO_LOAD_GRAPH') !== 'false',
};

/**
 * Utility function to build full URL from base and endpoint
 */
export const buildUrl = (endpoint, method) => {
  if (!endpoint || typeof endpoint !== 'string') {
    return '';
  }
  if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
    return endpoint;
  }
  const service = getServiceForPath(endpoint, method);
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

export default config;
export { config, baseConfig };
