import { normalizeCommonGraph } from '../../types/commonGraph';
import { getDiagramType } from '../registry/diagramRegistry';
import { layeredLayout } from '../layouts/basicLayouts';
import { validateGraphAgainstConfig } from '../../validation/diagramValidation';

export function createDiagramModel(inputGraph, diagramTypeId = 'uaf') {
  const config = getDiagramType(diagramTypeId);
  const graph = normalizeCommonGraph(inputGraph);
  const nodes = layeredLayout(graph.nodes, graph.links, config);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const links = graph.links.filter((link) => nodeIds.has(link.source) && nodeIds.has(link.target));
  return {
    config,
    graph: { nodes, links },
    validation: validateGraphAgainstConfig({ nodes, links }, config),
  };
}

export function mergeGraphSlice(baseGraph, sliceGraph) {
  const nodes = new Map((baseGraph.nodes || []).map((node) => [node.id, node]));
  const links = new Map((baseGraph.links || []).map((link) => [link.id, link]));
  (sliceGraph.nodes || []).forEach((node) => nodes.set(node.id, { ...(nodes.get(node.id) || {}), ...node }));
  (sliceGraph.links || []).forEach((link) => links.set(link.id, { ...(links.get(link.id) || {}), ...link }));
  return { nodes: [...nodes.values()], links: [...links.values()] };
}
