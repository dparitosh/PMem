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
    // The standalone graph service deliberately exposes bounded projections.
    // Contextual ranking stays in the UI, where it can apply the active view
    // and user search settings without falling back to the retired proxy.
    return this.getOverview(params.limit || 900, signal);
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
