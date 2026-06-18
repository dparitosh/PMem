import { API, buildUrl, replaceParams } from '../config';
import { apiClient } from './apiClient';

export const graphApi = {
  getOverview(limit = 900, signal) {
    return apiClient.get(API.graph.graphView ? buildUrl(API.graph.graphView) : buildUrl(API.graph.graphvis), {
      params: { limit },
      signal,
    });
  },
  getOntologyGraph(prefix, limit = 200, signal) {
    return apiClient.get(buildUrl(replaceParams(API.graph.graphOntologyView, { prefix })), {
      params: { limit },
      signal,
    });
  },
  getContextualSubgraph(params = {}, signal) {
    return apiClient.get(buildUrl(API.graph.contextualSubgraph), {
      params,
      signal,
    });
  },
  getTraversal(nodeId, depth = 2, signal) {
    return apiClient.get(buildUrl(replaceParams(API.graph.graphtraverseNode, { node_id: nodeId })), {
      params: { depth },
      signal,
    });
  },
  getStepParts(signal) {
    return apiClient.get(buildUrl(API.graph.stepParts), { signal });
  },
};

export default graphApi;
