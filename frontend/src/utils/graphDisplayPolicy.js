export const shouldRenderNodeLabels = (nodeCount, linkCount, graphSearchActive, graphViewMode = 'ontology') => {
  if (['ontology', 'individual'].includes(graphViewMode)) return true;
  if (graphSearchActive) return true;
  if (nodeCount > 220 || linkCount > 260) return false;
  return nodeCount > 0 || linkCount > 0;
};

export const getNodeLabelStyle = (nodeCount, graphViewMode = 'ontology') => {
  if (graphViewMode === 'ontology') {
    if (nodeCount > 220) {
      return { fontSize: 7, maxLength: 16 };
    }
    if (nodeCount > 150) {
      return { fontSize: 8, maxLength: 18 };
    }
    if (nodeCount > 80) {
      return { fontSize: 9, maxLength: 24 };
    }
    return { fontSize: 10, maxLength: 36 };
  }
  if (graphViewMode === 'individual') {
    return { fontSize: 11, maxLength: 42 };
  }
  if (nodeCount > 220) {
    return { fontSize: 0, maxLength: 0 };
  }
  if (nodeCount > 350) {
    return { fontSize: 7, maxLength: 14 };
  }
  if (nodeCount > 150) {
    return { fontSize: 7.5, maxLength: 16 };
  }
  if (nodeCount > 80) {
    return { fontSize: 8.5, maxLength: 22 };
  }
  return { fontSize: 10, maxLength: 36 };
};

export const shouldRenderRelationshipLabels = (nodeCount, linkCount, graphSearchActive, graphViewMode = 'ontology') => {
  if (graphViewMode === 'individual') return true;
  if (graphSearchActive) return linkCount <= 120;
  if (graphViewMode === 'ontology') return linkCount <= 180 && nodeCount <= 220;
  return linkCount <= 60 && nodeCount <= 80;
};

export const getRelationshipLabelStyle = (linkCount, graphViewMode = 'ontology') => {
  if (graphViewMode === 'ontology') {
    if (linkCount > 180) {
      return { fontSize: 7, maxLength: 16 };
    }
    if (linkCount > 120) {
      return { fontSize: 7.5, maxLength: 18 };
    }
    if (linkCount > 80) {
      return { fontSize: 8, maxLength: 22 };
    }
    return { fontSize: 9, maxLength: 32 };
  }
  if (graphViewMode === 'individual') {
    return { fontSize: 9, maxLength: 34 };
  }
  if (linkCount > 160) {
    return { fontSize: 0, maxLength: 0 };
  }
  if (linkCount > 180) {
    return { fontSize: 7, maxLength: 18 };
  }
  if (linkCount > 80) {
    return { fontSize: 8, maxLength: 24 };
  }
  return { fontSize: 9, maxLength: 32 };
};

export const truncateGraphLabel = (value, maxLength = 36) => {
  const label = String(value || '').trim();
  if (label.length <= maxLength) return label;
  return `${label.slice(0, Math.max(1, maxLength - 1))}…`;
};

export const buildNodeHighlightTerms = (node = {}) => {
  const props = node.properties && typeof node.properties === 'object' ? node.properties : node;
  return [
    props.name,
    props.title,
    props.label,
    props.code,
    props.key,
    props.identifier,
    props.requirement_id,
    props.part_number,
    node.name,
    node.title,
    node.label,
  ]
    .filter((value) => value != null && String(value).trim() !== '')
    .map((value) => String(value).trim().toLowerCase());
};
