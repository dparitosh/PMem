import { buildSemanticServiceUrl } from '../config';
import { apiClient } from './apiClient';

const graphUrl = (path) => buildSemanticServiceUrl('graph', path);

export const graphApi = {
  getOverview(limit = 900, signal) {
    return apiClient.get(graphUrl('/api/v1/graph/overview'), {
      params: { limit },
      signal,
    });
  },
  getOntologyGraph(prefix, limit = 200, signal) {
    return apiClient.get(graphUrl(`/api/v1/graph/ontologies/${encodeURIComponent(prefix)}/projection`), {
      params: { limit },
      signal,
    });
  },
  getArchitectureGraph(prefix = 'archimate', limit = 1000, signal) {
    return apiClient.get(graphUrl(`/api/v1/graph/ontologies/${encodeURIComponent(prefix)}/projection`), {
      params: { limit },
      signal,
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
    return apiClient.post(graphUrl('/api/v1/graphql'), { query, variables, operationName: 'ContextualSubgraph' }, { signal })
      .then((response) => ({ ...response, data: response.data?.data?.contextualResult || {} }));
  },
  getTraversal(nodeId, depth = 2, signal) {
    return apiClient.get(graphUrl(`/api/v1/graph/traversal/${encodeURIComponent(nodeId)}`), {
      params: { depth },
      signal,
    });
  },
  getStepParts(signal) {
    return this.getOntologyGraph('step', 900, signal);
  },
};

export default graphApi;
