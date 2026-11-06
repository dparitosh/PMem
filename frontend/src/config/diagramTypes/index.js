export const archimateDiagramType = {
  id: 'archimate',
  label: 'ArchiMate',
  description: 'Architecture and process model views from ArchiMate exchange data.',
  renderer: 'svg-fallback',
  explorerRenderer: 'cytoscape-or-d3',
  palette: ['Capability', 'BusinessFunction', 'BusinessProcess', 'BusinessObject', 'ApplicationComponent', 'Node', 'Artifact', 'Requirement', 'Document', 'Relationship'],
  layers: ['motivation', 'strategy', 'business', 'application', 'technology', 'implementation'],
  allowedRelationships: ['ACCESS', 'AGGREGATION', 'ASSIGNMENT', 'ASSOCIATION', 'COMPOSITION', 'FLOW', 'INFLUENCE', 'REALIZATION', 'SERVING', 'SPECIALIZATION', 'TRIGGERING'],
  requiredProperties: { default: ['name'], BusinessFunction: ['name'], BusinessProcess: ['name'] },
};

export const uafDiagramType = {
  id: 'uaf',
  label: 'UAF / MBSE',
  description: 'Capability, operational activity, resource, performer, requirement, function, interface, product, and part modeling.',
  renderer: 'svg-fallback',
  explorerRenderer: 'cytoscape-or-d3',
  palette: ['Capability', 'OperationalActivity', 'Resource', 'Performer', 'Requirement', 'Function', 'Interface', 'Product', 'Part', 'Document', 'Package', 'Relationship'],
  layers: ['capability', 'operational', 'resource', 'functional', 'product', 'requirements'],
  allowedRelationships: ['CONTAINS', 'SATISFIES', 'VERIFIES', 'ALLOCATED_TO', 'PERFORMS', 'COMPOSED_OF', 'REALIZES', 'INTERFACES_WITH', 'REFERENCES', 'TRACE_TO', 'DEPENDS_ON', 'IMPLEMENTS'],
  requiredProperties: { default: ['name'], Requirement: ['name', 'text'], Interface: ['name'], Part: ['name'] },
};

export const diagramTypeConfigs = [archimateDiagramType, uafDiagramType];
