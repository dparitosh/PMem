export const semanticMappings = {
  ArchiMate: {
    classToNode: {
      BusinessFunction: { type: 'BusinessFunction', layer: 'business' },
      BusinessProcess: { type: 'BusinessProcess', layer: 'business' },
      ApplicationComponent: { type: 'ApplicationComponent', layer: 'application' },
      Node: { type: 'Node', layer: 'technology' },
      Requirement: { type: 'Requirement', layer: 'motivation' },
    },
    objectPropertyToLink: {
      composition: 'COMPOSITION', aggregation: 'AGGREGATION', access: 'ACCESS', realization: 'REALIZATION', serving: 'SERVING', flow: 'FLOW', triggering: 'TRIGGERING', association: 'ASSOCIATION', specialization: 'SPECIALIZATION',
    },
    dataPropertyToPanel: ['name', 'label', 'documentation', 'description', 'identifier', 'source_filename'],
  },
  UAF: {
    classToNode: {
      Capability: { type: 'Capability', layer: 'capability' },
      OperationalActivity: { type: 'OperationalActivity', layer: 'operational' },
      Resource: { type: 'Resource', layer: 'resource' },
      Performer: { type: 'Performer', layer: 'resource' },
      Requirement: { type: 'Requirement', layer: 'requirements' },
      Function: { type: 'Function', layer: 'functional' },
      Part: { type: 'Part', layer: 'product' },
    },
    objectPropertyToLink: { satisfies: 'SATISFIES', verifies: 'VERIFIES', allocatedTo: 'ALLOCATED_TO', performs: 'PERFORMS', composedOf: 'COMPOSED_OF', realizes: 'REALIZES', interfacesWith: 'INTERFACES_WITH' },
    dataPropertyToPanel: ['name', 'text', 'rationale', 'owner', 'revision', 'status', 'source_filename'],
  },
};

export function mappingForProfile(profile = 'UAF') {
  return semanticMappings[profile] || semanticMappings.UAF;
}
