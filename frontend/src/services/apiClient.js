/**
 * Centralized API Client
 * Uses axios with configuration from environment variables
 * Provides typed endpoints for all backend API operations
 */

import axios from 'axios';
import { config, API, buildUrl, replaceParams } from '../config';
import logger from '../utils/logger';
import agenticAPI from './agenticApi';

/**
 * Create axios instance with base configuration
 */
const apiClient = axios.create({
  baseURL: config.backendUrl,
  timeout: config.requestTimeout || 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

const MAX_GET_RETRIES = 2;
const RETRY_BASE_DELAY_MS = 700;
const SESSION_STORAGE_KEY = 'depo.sessionId.v1';

export function getClientSessionId() {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage.getItem(SESSION_STORAGE_KEY) || null;
  } catch (_error) {
    return null;
  }
}

export function clearClientSessionId() {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch (_error) {
    // Restricted browser storage should not break conversation reset.
  }
}

export function setClientSessionId(sessionId) {
  if (!sessionId || typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, String(sessionId));
  } catch (_error) {
    // Restricted browser storage should not break API requests.
  }
}

function adoptServerSession(response) {
  const serverSessionId = response?.headers?.['x-session-id'];
  if (!serverSessionId || typeof window === 'undefined') return;
  try {
    setClientSessionId(serverSessionId);
  } catch (_error) {
    // Restricted browser storage should not break API requests.
  }
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isTransientNetworkError(error) {
  const code = String(error?.code || '').toUpperCase();
  const msg = String(error?.message || '').toLowerCase();
  return (
    code === 'ERR_NETWORK' ||
    code === 'ECONNABORTED' ||
    msg.includes('timeout') ||
    msg.includes('econnrefused') ||
    msg.includes('connection refused') ||
    msg.includes('econnreset') ||
    msg.includes('connection reset')
  );
}

/**
 * Request interceptor - Log requests in debug mode
 */
apiClient.interceptors.request.use(
  (requestConfig) => {
    const sessionId = getClientSessionId();
    if (sessionId) {
      requestConfig.headers = requestConfig.headers || {};
      requestConfig.headers['X-Session-ID'] = sessionId;
    }
    if (config.adminApiKey && String(requestConfig.url || '').includes('/api/v1/admin/')) {
      requestConfig.headers = requestConfig.headers || {};
      requestConfig.headers['X-API-Key'] = config.adminApiKey;
    }
    if (config.debug) {
      // eslint-disable-next-line no-console
      console.debug('[API] Request:', {
        method: requestConfig.method.toUpperCase(),
        url: requestConfig.url,
        data: requestConfig.data,
      });
    }
    return requestConfig;
  },
  (error) => {
    logger.error('[API] Request Error:', error);
    return Promise.reject(error);
  }
);

/**
 * Response interceptor - Log responses and handle errors
 */
apiClient.interceptors.response.use(
  (response) => {
    adoptServerSession(response);
    if (config.debug) {
      // eslint-disable-next-line no-console
      console.debug('[API] Response:', {
        status: response.status,
        url: response.config.url,
        data: response.data,
      });
    }
    return response;
  },
  async (error) => {
    const requestConfig = error?.config || {};
    const method = String(requestConfig.method || 'get').toLowerCase();
    const retryCount = requestConfig.__retryCount || 0;
    const canRetry = method === 'get' && !error?.response && isTransientNetworkError(error) && retryCount < MAX_GET_RETRIES;

    if (canRetry) {
      requestConfig.__retryCount = retryCount + 1;
      const backoff = RETRY_BASE_DELAY_MS * requestConfig.__retryCount;
      if (config.debug) {
        logger.warn(`[API] transient network error, retry ${requestConfig.__retryCount}/${MAX_GET_RETRIES}:`, {
          url: requestConfig.url,
          method,
          backoff,
          message: error.message,
        });
      }
      await wait(backoff);
      return apiClient(requestConfig);
    }

    const errorInfo = {
      status: error.response?.status,
      message: error.message,
      errorCode: error.response?.data?.error_code,
      detail: error.response?.data?.detail || error.response?.data?.message,
      url: error.config?.url,
      data: error.response?.data,
    };

    // Keep the backend's standardized error contract available to all callers.
    error.apiError = {
      status: errorInfo.status,
      code: errorInfo.errorCode,
      message: errorInfo.detail || errorInfo.message,
      path: error.response?.data?.path,
    };

    if (config.debug) {
      logger.error('[API] Response Error:', errorInfo);
    }

    // Handle specific status codes
    if (error.response?.status === 401) {
      // Unauthorized - could trigger logout
      // dispatch(logout());
    } else if (error.response?.status === 403) {
      logger.warn('[API] Access forbidden');
    } else if (error.response?.status === 404) {
      logger.warn('[API] Resource not found');
    } else if (error.response?.status === 500) {
      logger.error('[API] Server error');
    } else if (error.response?.status === 503) {
      logger.warn('[API] Service unavailable:', errorInfo.errorCode || errorInfo.detail);
    } else if (error.response?.status === 504) {
      logger.warn('[API] Service timeout:', errorInfo.errorCode || errorInfo.detail);
    }

    return Promise.reject(error);
  }
);

/**
 * API Methods organized by category
 */

// ========== HEALTH & STATUS ==========
export const healthAPI = {
  check: (options = {}) => apiClient.get(buildUrl(API.health.health), options),
  ready: (options = {}) => apiClient.get(buildUrl(API.health.ready), options),
  graphMetrics: () => apiClient.get(buildUrl(API.health.graphMetrics)),
  ontologiesAvailable: () => apiClient.get(buildUrl(API.health.ontologiesAvailable)),
};

// ========== GRAPH ENDPOINTS ==========
export const graphAPI = {
  getGraph: () => apiClient.get(buildUrl(API.graph.graphvis)),
  filterGraph: (searchTerm) => 
    apiClient.post(buildUrl(API.graph.graphfilter), { search: searchTerm }),
  filterMulti: (filters) => 
    apiClient.post(buildUrl(API.graph.graphfilterMulti), filters),
  traverse: (nodeId, options = {}) =>
    apiClient.get(buildUrl(replaceParams(API.graph.graphtraverseNode, { node_id: nodeId })), options),
  getSchemaGraph: () => apiClient.get(buildUrl(API.graph.schemaGraph)),
  getInstanceGraph: () => apiClient.get(buildUrl(API.graph.instanceGraph)),
  getOntologyInstances: (ontologyId, params = {}) =>
    apiClient.get(buildUrl(replaceParams(API.graph.ontologyInstances, { ontology: ontologyId })), { params }),
};

// ========== SCHEMA ENDPOINTS ==========
export const schemaAPI = {
  getSchema: () => apiClient.get(buildUrl(API.schema.schema)),
  getAP242RotorPmi: () => apiClient.get(buildUrl(API.schema.ap242RotorPmi)),
  searchAP242: (query) => 
    apiClient.post(buildUrl(API.schema.ap242Search), { query }),
  getReports: (type, page = 1, pageSize = 10) =>
    apiClient.post(buildUrl(API.schema.reports), { type, page, page_size: pageSize }),
};

// ========== CHAT ENDPOINTS ==========
export const chatAPI = {
  sendMessage: (message, sessionId = null, graphContext = null) =>
    apiClient.post(buildUrl(API.chat.chat), { message, session_id: sessionId, graph_context: graphContext }),
  streamChat: (message, sessionId = null, graphContext = null) =>
    apiClient.post(buildUrl(API.chat.chatStream), { message, session_id: sessionId, graph_context: graphContext }),
  validate: (message, sessionId = null, graphContext = null) =>
    apiClient.post(buildUrl(API.chat.validate), { message, session_id: sessionId, graph_context: graphContext }),
  submitJob: (message, sessionId = null, graphContext = null) =>
    apiClient.post(buildUrl(API.chat.jobs), { message, session_id: sessionId, graph_context: graphContext }),
  getJob: (jobId) => apiClient.get(buildUrl(replaceParams(API.chat.jobStatus, { job_id: jobId }))),
  health: () => apiClient.get(buildUrl(API.chat.health)),
  status: () => apiClient.get(buildUrl(API.chat.status)),
  capabilities: () => apiClient.get(buildUrl(API.chat.capabilities)),
  sampleQueries: () => apiClient.get(buildUrl(API.chat.sampleQueries)),
};

// ========== ONTOLOGY ENDPOINTS ==========
export const ontologyAPI = {
  upload: (file, metadata) => {
    const formData = new FormData();
    formData.append('file', file);
    
    // Convert camelCase keys to snake_case for backend compatibility
    const keyMap = {
      ontologyName: 'ontology_name',
      generationType: 'generation_type',
      schemaType: 'schema_type',
    };
    
    Object.entries(metadata).forEach(([key, value]) => {
      const backendKey = keyMap[key] || key;
      formData.append(backendKey, value);
    });
    
    return apiClient.post(buildUrl(API.ontology.upload), formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000, // 5 minutes for ontology uploads
    });
  },
  listRegistered: (options = {}) =>
    apiClient.get(buildUrl(API.ontology.registered), options),
  get: (ontologyId) => 
    apiClient.get(buildUrl(replaceParams(API.ontology.get, { ontology: ontologyId }))),
  getDataDictionary: (ontologyId, options = {}) =>
    apiClient.get(buildUrl(replaceParams(API.ontology.dataDictionary, { ontology: ontologyId })), options),
  getTaxonomy: (ontologyId) =>
    apiClient.get(buildUrl(replaceParams(API.ontology.taxonomy, { ontology: ontologyId }))),
  getReasoning: (ontologyId) =>
    apiClient.get(buildUrl(replaceParams(API.ontology.reason, { ontology: ontologyId }))),
  previewInference: (ontologyId, payload = {}) =>
    apiClient.post(buildUrl(replaceParams(API.ontology.inferencePreview, { ontology: ontologyId })), payload),
  validateSkos: (payload) => apiClient.post(buildUrl(API.ontology.skosValidate), payload),
  searchSkos: (payload) => apiClient.post(buildUrl(API.ontology.skosSearch), payload),
  traverseSkos: (payload) => apiClient.post(buildUrl(API.ontology.skosTraverse), payload),
  skosStoragePlan: (payload) => apiClient.post(buildUrl(API.ontology.skosStoragePlan), payload),
  validateRule: (payload) => apiClient.post(buildUrl(API.ontology.ruleValidate), payload),
  executeRulePreview: (payload) => apiClient.post(buildUrl(API.ontology.ruleExecutePreview), payload),
  ruleMaterializationPlan: (payload) => apiClient.post(buildUrl(API.ontology.ruleMaterializationPlan), payload),
  getMappings: (ontologyId, mappingType) => 
    apiClient.get(buildUrl(replaceParams(API.ontology.mappings, { 
      ontology: ontologyId, 
      type: mappingType 
    }))),
  mapEntity: (ontologyId, mappingData) => 
    apiClient.post(buildUrl(replaceParams(API.ontology.mapEntity, { ontology: ontologyId })), mappingData),
  getAlignmentOptions: (fileType = '') => {
    const suffix = fileType ? `?file_type=${encodeURIComponent(fileType)}` : '';
    return apiClient.get(buildUrl(`${API.ontology.alignmentOptions}${suffix}`));
  },
  merge: (fromOntologyId, toOntologyId, options = {}) =>
    apiClient.post(buildUrl(API.ontology.merge), {
      from_ontology_id: fromOntologyId,
      to_ontology_id: toOntologyId,
      ...(options || {}),
    }),
  cleanupOldXsd: (body) => apiClient.post(buildUrl(API.ontology.cleanupOldXsd), body),
  exportUrl: (ontologyId, format = 'ttl') => `${buildUrl(replaceParams(API.ontology.exportRegistered, { ontology: ontologyId }))}?format=${encodeURIComponent(format)}`,
  exportRegistered: (ontologyId, format = 'ttl') =>
    apiClient.get(buildUrl(replaceParams(API.ontology.exportRegistered, { ontology: ontologyId })), { params: { format }, responseType: 'blob' }),
  extract3dxml: (file, metadata = {}) => {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(metadata).forEach(([key, value]) => {
      formData.append(key, value);
    });
    return apiClient.post(buildUrl(API.ontology.extract3dxml), formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    });
  },
  get3dxmlStatus: (taskId) =>
    apiClient.get(buildUrl(replaceParams(API.ontology.threeDxmlStatus, { task_id: taskId }))),
  get3dxmlFormats: () => apiClient.get(buildUrl(API.ontology.threeDxmlFormats)),
};

// ========== DATA IMPORT ENDPOINTS ==========
export const importAPI = {
  upload: (file, metadata = {}) => {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(metadata).forEach(([key, value]) => {
      formData.append(key, value);
    });
    return apiClient.post(buildUrl(API.import.upload), formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000, // 5 minutes for file uploads
    });
  },
  getStatus: (taskId) => 
    apiClient.get(buildUrl(replaceParams(API.import.status, { task_id: taskId }))),
  getPreview: (taskId) => 
    apiClient.get(buildUrl(replaceParams(API.import.preview, { task_id: taskId }))),
  getTasks: () =>
    apiClient.get(buildUrl(API.import.tasks)),
  commit: (taskId, options = {}) => 
    apiClient.post(buildUrl(replaceParams(API.import.commit, { task_id: taskId })), options, {
      timeout: 300000, // 5 minutes — Neo4j batch commit to AuraDB can take 2-3 min
    }),
  preCommitCheck: (taskId) =>
    apiClient.get(buildUrl(replaceParams(API.import.preCommit, { task_id: taskId })), { timeout: 300000 }),
  cancel: (taskId) => 
    apiClient.post(buildUrl(replaceParams(API.import.cancel, { task_id: taskId }))),
  getOWL: (taskId) => 
    apiClient.get(buildUrl(replaceParams(API.import.owl, { task_id: taskId }))),
  exportOWL: (taskId, format = 'ttl') =>
    apiClient.get(buildUrl(replaceParams(API.import.owlExport, { task_id: taskId })), { params: { format }, responseType: 'blob' }),
  getFormats: () => apiClient.get(buildUrl(API.import.formats)),
  queryOllama: (query) => 
    apiClient.post(buildUrl(API.import.ollamaQuery), { query }),
  checkOllamaHealth: () => apiClient.get(buildUrl(API.import.ollamaHealth)),
};

// ========== WORKFLOW ENDPOINTS ==========
export const workflowAPI = {
  getOptions: () => apiClient.get(buildUrl(API.workflow.options)),
  execute: (workflowId, payload = {}) =>
    apiClient.post(buildUrl(API.workflow.execute), {
      workflow_id: workflowId,
      payload,
    }, {
      timeout: 300000,
    }),
  artifactUrl: (taskId, artifactPath) =>
    buildUrl(replaceParams(API.workflow.artifactFile, {
      task_id: taskId,
      artifact_path: artifactPath,
    }, { pathParams: ['artifact_path'] })),
};

// ========== INGESTION ENDPOINTS ==========
export const ingestionAPI = {
  ingestData: (data) => 
    apiClient.post(buildUrl(API.ingestion.ingestData), data),
};

// ========== DOCUMENT ENDPOINTS ==========
export const documentAPI = {
  getSupportedFormats: () => apiClient.get(buildUrl(API.document.formats)),
  upload: (files, metadata = {}) => {
    const formData = new FormData();
    if (Array.isArray(files)) {
      files.forEach((file) => formData.append('files', file));
    } else {
      formData.append('files', files);
    }
    Object.entries(metadata).forEach(([key, value]) => {
      formData.append(key, value);
    });
    return apiClient.post(buildUrl(API.document.upload), formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  uploadSingle: (file, metadata = {}) => {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(metadata).forEach(([key, value]) => {
      formData.append(key, value);
    });
    return apiClient.post(buildUrl(API.document.uploadSingle), formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  submitJob: (files, metadata = {}) => {
    const formData = new FormData();
    (Array.isArray(files) ? files : [files]).forEach((file) => formData.append('files', file));
    Object.entries(metadata).forEach(([key, value]) => formData.append(key, value));
    return apiClient.post(buildUrl(API.document.jobs), formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getJob: (taskId) => apiClient.get(buildUrl(replaceParams(API.document.job, { task_id: taskId }))),
  cancelJob: (taskId) => apiClient.post(buildUrl(replaceParams(API.document.cancelJob, { task_id: taskId }))),
  getJobArtifacts: (taskId) => apiClient.get(buildUrl(replaceParams(API.document.jobArtifacts, { task_id: taskId }))),
  checkHealth: () => apiClient.get(buildUrl(API.document.health)),
};

// ========== ADMIN ENDPOINTS ==========
export const adminAPI = {
  health: (options = {}) => apiClient.get(buildUrl(API.admin.health), options),
  registry: (options = {}) => apiClient.get(buildUrl(API.admin.registry), options),
  cleanSchema: () =>
    apiClient.post(buildUrl(API.admin.cleanSchema), { confirm: 'CLEAN_NEO4J_SCHEMA' }),
  clearCache: () => apiClient.post(buildUrl(API.admin.clearCache)),
  deleteData: ({ label, prefix, property, value, batchSize = 10000, dryRun = false }) =>
    apiClient.post(buildUrl(API.admin.deleteData), {
      label: label || null,
      prefix: prefix || null,
      property: property || null,
      value: property ? value : null,
      batch_size: batchSize,
      dry_run: dryRun,
      confirm: 'DELETE_NEO4J_DATA',
    }, {
      timeout: 300000,
    }),
  schemaStats: (options = {}) => apiClient.get(buildUrl(API.admin.schemaStats), options),
  resetDatabase: (recreateIndexes = true) =>
    apiClient.post(buildUrl(API.admin.resetDatabase), null, { params: { recreate_indexes: recreateIndexes } }),
};

export const metadataRegistryAPI = {
  list: (params = {}, options = {}) => apiClient.get(buildUrl(API.metadataRegistry.assets), { ...options, params }),
  get: (assetId) => apiClient.get(buildUrl(replaceParams(API.metadataRegistry.asset, { asset_id: assetId }))),
  create: (payload, options = {}) => apiClient.post(buildUrl(API.metadataRegistry.assets), payload, options),
  update: (assetId, payload) => apiClient.patch(buildUrl(replaceParams(API.metadataRegistry.asset, { asset_id: assetId })), payload),
  transition: (assetId, payload, options = {}) => apiClient.post(buildUrl(replaceParams(API.metadataRegistry.transition, { asset_id: assetId })), payload, options),
  history: (assetId, params = {}) => apiClient.get(buildUrl(replaceParams(API.metadataRegistry.history, { asset_id: assetId })), { params }),
};


// ========== REQUIREMENTS ENDPOINTS ==========
export const requirementsAPI = {
  list: (params = {}) => apiClient.get(buildUrl(API.requirements.list), { params }),
};


// ========== MODELING WORKBENCH ENDPOINTS ==========
export const modelingAPI = {
  metamodel: () => apiClient.get(buildUrl(API.modeling.metamodel)),
  ensureIndexes: () => apiClient.post(buildUrl(API.modeling.indexes)),
  graph: (params = {}, signal) => apiClient.get(buildUrl(API.modeling.graph), { params, signal }),
  tree: (params = {}) => apiClient.get(buildUrl(API.modeling.tree), { params }),
  search: (params = {}) => apiClient.get(buildUrl(API.modeling.search), { params }),
  context: (elementId, params = {}) => apiClient.get(buildUrl(replaceParams(API.modeling.context, { element_id: elementId })), { params }),
  createNode: (payload) => apiClient.post(buildUrl(API.modeling.nodes), payload),
  updateNode: (elementId, payload) => apiClient.put(buildUrl(replaceParams(API.modeling.node, { element_id: elementId })), payload),
  deleteNode: (elementId) => apiClient.delete(buildUrl(replaceParams(API.modeling.node, { element_id: elementId }))),
  createLink: (payload) => apiClient.post(buildUrl(API.modeling.links), payload),
  updateLink: (elementId, payload) => apiClient.put(buildUrl(replaceParams(API.modeling.link, { element_id: elementId })), payload),
  deleteLink: (elementId) => apiClient.delete(buildUrl(replaceParams(API.modeling.link, { element_id: elementId }))),
  validation: (params = {}) => apiClient.get(buildUrl(API.modeling.validation), { params }),
  seed: (payload = {}) => apiClient.post(buildUrl(API.modeling.seed), payload),
  createAgentProposal: (payload) => apiClient.post(buildUrl(API.modeling.agentProposals), payload),
  listAgentProposals: (params = {}) => apiClient.get(buildUrl(API.modeling.agentProposals), { params }),
  approveAgentProposal: (proposalId, payload = {}) => apiClient.post(buildUrl(replaceParams(API.modeling.agentProposalApprove, { proposal_id: proposalId })), payload),
  rejectAgentProposal: (proposalId, payload = {}) => apiClient.post(buildUrl(replaceParams(API.modeling.agentProposalReject, { proposal_id: proposalId })), payload),
};

// ========== RECOMMENDATION ENDPOINTS ==========
export const recommendationsAPI = {
  changeImpact: (changeName, scope = {}) =>
    apiClient.post(buildUrl(API.recommendations.changeImpact), {
      change_name: changeName,
      ...(scope?.ontology_id || scope?.ontology_ids || scope?.prefix || scope?.prefixes ? { scope } : {}),
    }),
  similarParts: (partName, topN = 10, scope = {}) =>
    apiClient.post(buildUrl(API.recommendations.similarParts), {
      part_name: partName,
      top_n: topN,
      ...(scope?.ontology_id || scope?.ontology_ids || scope?.prefix || scope?.prefixes ? { scope } : {}),
    }),
  manufacturing: (partName, scope = {}) =>
    apiClient.post(buildUrl(API.recommendations.manufacturing), {
      part_name: partName,
      ...(scope?.ontology_id || scope?.ontology_ids || scope?.prefix || scope?.prefixes ? { scope } : {}),
    }),
  health: () => apiClient.get(buildUrl(API.recommendations.health)),
};

/**
 * Export unified API object for convenience
 */
export const API_METHODS = {
  health: healthAPI,
  graph: graphAPI,
  schema: schemaAPI,
  chat: chatAPI,
  ontology: ontologyAPI,
  import: importAPI,
  workflow: workflowAPI,
  ingestion: ingestionAPI,
  document: documentAPI,
  admin: adminAPI,
  metadataRegistry: metadataRegistryAPI,
  recommendations: recommendationsAPI,
  requirements: requirementsAPI,
  modeling: modelingAPI,
  agentic: agenticAPI,
};

/**
 * Export raw axios client for custom requests
 */
export { apiClient };

export default apiClient;
