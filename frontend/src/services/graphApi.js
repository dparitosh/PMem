import { getServiceAuthToken } from './serviceAuth';
import { buildSemanticServiceUrl } from '../config';
import { apiClient } from './apiClient';

const readHeaders = () => {
  const token = getServiceAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const graphUrl = (path) => buildSemanticServiceUrl('graph', path);

export const graphApi = {
  getMetrics(ontologyId = '', signal, ontologyPrefix = '') {
    return apiClient.get(graphUrl('/api/v1/graph/metrics'), {
      params: { ontology_id: ontologyId, ontology_prefix: ontologyPrefix }, signal, timeout: 20000, headers: readHeaders(),
    });
  },
  verifyAccess(token) {
    // Verification must not depend on stale or unresolved imported metadata.
    return apiClient.get(graphUrl('/api/v1/graph/access'), {
      headers: { Authorization: `Bearer ${String(token || '').trim()}` },
      timeout: 15000,
    });
  },
  getOverview(limit = 900, signal) {
    return apiClient.get(graphUrl('/api/v1/graph/overview'), {
      params: { limit },
      signal,
      headers: readHeaders(),
    });
  },
  getOntologyGraph(prefix, limit = 200, signal) {
    return apiClient.get(graphUrl(`/api/v1/graph/ontologies/${encodeURIComponent(prefix)}/projection`), {
      params: { limit },
      signal,
      headers: readHeaders(),
    });
  },
  getArchitectureGraph(prefix = 'archimate', limit = 1000, signal) {
    return apiClient.get(graphUrl(`/api/v1/graph/ontologies/${encodeURIComponent(prefix)}/projection`), {
      params: { limit },
      signal,
      headers: readHeaders(),
    });
  },
  getContextualSubgraph(params = {}, signal) {
    const query = `query ContextualSubgraph($search: String!, $ontologyPrefix: String, $importId: String, $limit: Int, $searchMode: String, $expandNeighbors: Boolean) {
      contextualResult(search: $search, ontologyPrefix: $ontologyPrefix, importId: $importId, limit: $limit, searchMode: $searchMode, expandNeighbors: $expandNeighbors) {
        nodes { elementId label type labels properties canTraverse }
        relationships { elementId source target type properties }
        counts
        view
        root { elementId label type labels properties canTraverse }
      }
    }`;
    const variables = {
      search: String(params.search || ''),
      ontologyPrefix: params.ontology_prefix || '',
      importId: params.import_id || '',
      limit: params.limit || 200,
      searchMode: params.search_mode || 'best',
      expandNeighbors: Boolean(params.expand_neighbors),
    };
    return apiClient.post(graphUrl('/api/v1/graphql'), { query, variables, operationName: 'ContextualSubgraph' }, { signal, headers: readHeaders() })
      .then((response) => {
        if (response.data?.errors?.length) {
          throw new Error('Contextual graph query failed. Check graph service logs and access permissions.');
        }
        const result = response.data?.data?.contextualResult;
        if (!result) throw new Error('Graph service returned no contextual result.');
        return { ...response, data: result };
      });
  },
  getTraversal(nodeId, depth = 2, signal) {
    return apiClient.get(graphUrl(`/api/v1/graph/traversal/${encodeURIComponent(nodeId)}`), {
      params: { depth },
      signal,
      headers: readHeaders(),
    });
  },
  getStepParts(signal) {
    return this.getOntologyGraph('step', 900, signal);
  },
};

export default graphApi;
