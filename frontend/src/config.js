/**
 * API Configuration - Centralized endpoint mapping
 * All backend API endpoints are configured here via environment variables
 * This allows easy switching between environments without code changes
 */

// Base configuration
const baseConfig = {
  backendUrl: process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000',
  apiVersion: process.env.REACT_APP_API_VERSION || 'v1',
  environment: process.env.REACT_APP_ENV || 'development',
  debug: process.env.REACT_APP_DEBUG === 'true',
  logLevel: process.env.REACT_APP_LOG_LEVEL || 'info',
  requestTimeout: parseInt(process.env.REACT_APP_REQUEST_TIMEOUT || '30000', 10),
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
};

/**
 * Graph Visualization Endpoints
 */
const GRAPH_ENDPOINTS = {
  graphvis: process.env.REACT_APP_API_GRAPHVIS || '/graphvis',
  graphvisByOntology: process.env.REACT_APP_API_GRAPHVIS_BY_ONTOLOGY || '/graphvis/by-ontology/{prefix}',
  ontologiesList: process.env.REACT_APP_API_ONTOLOGIES_LIST || '/ontologies/list',
  neo4jHealth: process.env.REACT_APP_API_NEO4J_HEALTH || '/health/neo4j',
  graphfilter: process.env.REACT_APP_API_GRAPHFILTER || '/graphfilter',
  graphfilterMulti: process.env.REACT_APP_API_GRAPHFILTER_MULTI || '/graphfilter-multi',
  graphtraverse: process.env.REACT_APP_API_GRAPHTRAVERSE || '/graphtraverse',
  graphtraverseNode: process.env.REACT_APP_API_GRAPHTRAVERSE_NODE || '/graphtraverse/{node_id}',
  comparativeSearch: process.env.REACT_APP_API_COMPARATIVE_SEARCH || '/comparative-search',
  stepParts: process.env.REACT_APP_API_STEP_PARTS || '/ontology/step/parts',
  ontologyGraph: process.env.REACT_APP_API_ONTOLOGY_GRAPH || '/ontology/{ontology}',
  ontologyInstances: process.env.REACT_APP_API_ONTOLOGY_INSTANCES || '/ontology/{ontology}/instances',
  ontologyStepPart: process.env.REACT_APP_API_ONTOLOGY_STEP_PART || '/ontology/step/{part}',
  ontologyMbseInstances: process.env.REACT_APP_API_ONTOLOGY_MBSE_INSTANCES || '/ontology/mbse-instances',
};

/**
 * Schema & Metadata Endpoints
 */
const SCHEMA_ENDPOINTS = {
  schema: process.env.REACT_APP_API_SCHEMA || '/schema',
  ap242RotorPmi: process.env.REACT_APP_API_AP242_ROTOR_PMI || '/ap242/rotor-shaft-pmi',
  ap242Search: process.env.REACT_APP_API_AP242_SEARCH || '/ap242/search',
};

/**
 * Chat & Conversation Endpoints
 */
const CHAT_ENDPOINTS = {
  chat: process.env.REACT_APP_API_CHAT || '/chat',
  chatStream: process.env.REACT_APP_API_CHAT_STREAM || '/chat-stream',
};

/**
 * Ontology Management Endpoints (v1)
 */
const ONTOLOGY_ENDPOINTS = {
  upload: process.env.REACT_APP_API_ONTOLOGY_UPLOAD || '/api/v1/ontology/upload',
  registered: process.env.REACT_APP_API_ONTOLOGY_REGISTERED || '/api/v1/ontology/registered',
  get: process.env.REACT_APP_API_ONTOLOGY_GET || '/api/v1/ontology',
  dataDictionary: process.env.REACT_APP_API_ONTOLOGY_DATA_DICTIONARY || '/api/v1/ontology/{ontology}/data-dictionary',
  mappings: process.env.REACT_APP_API_ONTOLOGY_MAPPINGS || '/api/v1/ontology/{ontology}/mappings/{type}',
  mapEntity: process.env.REACT_APP_API_ONTOLOGY_MAP_ENTITY || '/api/v1/ontology/{ontology}/map-entity',
  alignmentOptions: process.env.REACT_APP_API_ONTOLOGY_ALIGNMENT_OPTIONS || '/ontology-mappings',
  // Legacy endpoints for backward compatibility
  uploadLegacy: process.env.REACT_APP_API_ONTOLOGY_UPLOAD_LEGACY || '/api/ontology/upload',
  registeredLegacy: process.env.REACT_APP_API_ONTOLOGY_REGISTERED_LEGACY || '/api/ontology/registered',
};

/**
 * Data Import Endpoints (v1)
 */
const IMPORT_ENDPOINTS = {
  upload: process.env.REACT_APP_API_IMPORT_UPLOAD || '/api/v1/import/upload',
  status: process.env.REACT_APP_API_IMPORT_STATUS || '/api/v1/import/status/{task_id}',
  preview: process.env.REACT_APP_API_IMPORT_PREVIEW || '/api/v1/import/preview/{task_id}',
  commit: process.env.REACT_APP_API_IMPORT_COMMIT || '/api/v1/import/commit/{task_id}',
  cancel: process.env.REACT_APP_API_IMPORT_CANCEL || '/api/v1/import/cancel/{task_id}',
  owl: process.env.REACT_APP_API_IMPORT_OWL || '/api/v1/import/owl/{task_id}',
  convertSchema: process.env.REACT_APP_API_IMPORT_CONVERT_SCHEMA || '/api/v1/import/convert-schema',
  parseSchema: process.env.REACT_APP_API_IMPORT_PARSE_SCHEMA || '/api/v1/import/parse-schema',
  processStages: process.env.REACT_APP_API_IMPORT_PROCESS_STAGES || '/api/v1/import/process-stages-4-7',
  formats: process.env.REACT_APP_API_IMPORT_FORMATS || '/api/v1/import/formats',
  ollamaQuery: process.env.REACT_APP_API_IMPORT_OLLAMA_QUERY || '/api/v1/import/ollama/query',
  ollamaHealth: process.env.REACT_APP_API_IMPORT_OLLAMA_HEALTH || '/api/v1/import/ollama/health',
  mapOntology: process.env.REACT_APP_API_IMPORT_MAP_ONTOLOGY || '/api/v1/import/map-ontology',
  // Legacy endpoints for backward compatibility
  uploadLegacy: process.env.REACT_APP_API_IMPORT_UPLOAD_LEGACY || '/api/import/upload',
  statusLegacy: process.env.REACT_APP_API_IMPORT_STATUS_LEGACY || '/api/import/status/{task_id}',
};

/**
 * Ingestion Endpoints (v1)
 */
const INGESTION_ENDPOINTS = {
  ingestData: process.env.REACT_APP_API_INGEST_DATA || '/api/v1/ingestion/ingest-data',
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
  ingestion: INGESTION_ENDPOINTS,
  document: DOCUMENT_ENDPOINTS,
  ui: UI_CONFIG,
};

// Log configuration in development
if (baseConfig.debug) {
  // eslint-disable-next-line no-console
  console.info('[CONFIG] API Configuration Loaded:', {
    environment: baseConfig.environment,
    backendUrl: baseConfig.backendUrl,
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
if (!config.backendUrl) {
  // eslint-disable-next-line no-console
  console.warn('[CONFIG] Missing REACT_APP_BACKEND_URL. Using default: http://localhost:8000');
}

export default config;
export { config, baseConfig };
