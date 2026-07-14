const getLinkEndpointId = (endpoint) => {
  if (!endpoint) return null;
  if (typeof endpoint === 'object') {
    return endpoint.elementId || endpoint.id || endpoint.identity || endpoint._id || null;
  }
  return endpoint;
};

export const normalizeSearchTerm = (value = '') => String(value || '')
  .trim()
  .toLowerCase()
  .replace(/\*+/g, '')
  .replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, '');

export const normalizeRelationshipType = (value = '') => {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const normalized = raw.replace(/[\s-]+/g, '_').toUpperCase();
  const aliases = {
    MASTERREF: 'MASTER_REFERENCE',
    MASTER_REFERENCE: 'MASTER_REFERENCE',
    RELATEDREF: 'RELATED_REFERENCE',
    RELATEDREFS: 'RELATED_REFERENCE',
    RELATED_REFERENCE: 'RELATED_REFERENCE',
    PARTREF: 'PART_REFERENCE',
    PART_REF: 'PART_REFERENCE',
    PARTREFERENCE: 'PART_REFERENCE',
    INSTANCEREF: 'INSTANCE_REFERENCE',
    INSTANCEREFS: 'INSTANCE_REFERENCE',
    INSTANCE_REF: 'INSTANCE_REFERENCE',
    INSTANCE_REFS: 'INSTANCE_REFERENCE',
    HAS_CHILD_INSTANCE: 'HAS_CHILD_INSTANCE',
    HAS_PARENT_INSTANCE: 'HAS_PARENT_INSTANCE',
    PARENTREF: 'PARENT_REFERENCE',
    SEG0SATISFY: 'SATISFIES',
    SATISFY: 'SATISFIES',
    GENERALRELATION: 'GENERAL_RELATION',
    TRACE: 'TRACE_LINK',
    TRACE_LINK: 'TRACE_LINK',
  };
  return aliases[normalized] || normalized;
};

const CAD_SEMANTIC_ROLES = new Set([
  'product',
  'shape',
  'feature',
  'representation',
  'topology',
  'geometry',
  'dimension_tolerance',
  'geometric_tolerance',
  'datum',
  'dimension',
  'annotation',
  'surface_finish',
]);

const STEP_INSTANCE_LABELS = new Set([
  'product',
  'product_definition',
  'product_definition_formation',
  'product_definition_shape',
  'shape_representation',
  'shape_aspect',
  'shape_aspect_relationship',
  'shape_definition_representation',
  'feature_component_definition',
  'instanced_feature',
  'feature_pattern',
  'advanced_brep_shape_representation',
  'part',
  'partversion',
  'part_version',
  'partview',
  'part_view',
  'view',
  'views',
  'geometric_model',
  'occurrence',
  'view_occurrence_relationship',
  'placement',
  'cartesian_transformation',
  'rotation_matrix',
  'translation_vector',
  'geometric_tolerance',
  'plus_minus_tolerance',
  'tolerance_value',
  'datum_feature',
  'datum_target',
  'datum_reference',
  'dimensional_size',
  'dimensional_location',
  'angular_location',
  'annotation_text_occurrence',
  'draughting_callout',
  'presentation_style_assignment',
  'text_literal',
  'leader_curve',
  'styled_item',
  'surface_texture_representation',
]);

export const isCadBusinessObjectNode = (node) => {
  if (!node) return false;
  const labels = Array.isArray(node?.labels)
    ? node.labels.map((label) => String(label || '').toLowerCase())
    : [];
  const props = node?.properties && typeof node.properties === 'object' ? node.properties : {};
  const semanticRole = String(props.semantic_role || '').trim().toLowerCase();
  return Boolean(props.is_cad_business_object)
    || CAD_SEMANTIC_ROLES.has(semanticRole)
    || labels.some((label) => STEP_INSTANCE_LABELS.has(label));
};

export const isMetadataWrapperNode = (node) => {
  if (!node) return false;
  const labels = Array.isArray(node?.labels)
    ? node.labels.map((label) => String(label || '').toLowerCase())
    : [];
  const props = node?.properties && typeof node.properties === 'object' ? node.properties : {};
  const displayName = String(
    props.name ||
    props.title ||
    props.label ||
    node?.name ||
    node?.label ||
    ''
  ).trim().toLowerCase();
  const type = String(
    props.type ||
    props.entity_type ||
    props.sub_type ||
    node?.type ||
    node?.label ||
    ''
  ).trim().toLowerCase();
  const technicalInstanceLabels = [
    'productinstance',
    'occurrence',
    'connectioninstance',
    'productview',
    'attributecontext',
  ];
  const hasBusinessIdentity = Boolean(
    props.catalogue_id ||
    props.requirement_id ||
    props.requirement_ref ||
    props.part_number ||
    props.product_name ||
    props.title ||
    props.code
  );

  if (isCadBusinessObjectNode(node)) {
    return false;
  }

  const hasKnownBusinessLabel = labels.some((label) => [
    'part',
    'partversion',
    'part_occurrence',
    'product',
    'productrevision',
    'productinstance',
    'processinstance',
    'occurrence',
    'requirement',
    'requirementrevision',
    'connection',
    'connectionrevision',
    'connectioninstance',
    'ontologyclass',
    'ontologyproperty',
    'individual',
    'class',
    'objectproperty',
    'datatypeproperty',
  ].includes(label));

  if (/^id[\w:-]*$/i.test(displayName) || /^id\d+$/i.test(displayName)) {
    if (labels.some((label) => technicalInstanceLabels.includes(label)) && !hasBusinessIdentity) {
      return true;
    }
    // An id-like display value is common in PLM/XML data and is not sufficient
    // evidence that a typed business object is merely a metadata wrapper.
    return !hasBusinessIdentity && !hasKnownBusinessLabel;
  }

  if (hasKnownBusinessLabel) {
    return false;
  }

  if (displayName && labels.some((label) => ['xmltag', 'xmlnode', 'metadatawrapper', 'documentfragment'].includes(label))) {
    return true;
  }

  return [
    'accessintent',
    'xmltag',
    'xmlnode',
    'metadata',
    'metadatawrapper',
    'documentfragment',
  ].includes(type) || labels.some((label) => [
    'accessintent',
    'xmltag',
    'xmlnode',
    'metadata',
    'metadatawrapper',
    'documentfragment',
  ].includes(label));
};

export const isRelationshipCarrierNode = (node) => {
  if (!node) return false;
  const labels = Array.isArray(node?.labels)
    ? node.labels.map((label) => String(label || '').toLowerCase())
    : [];
  const props = node?.properties && typeof node.properties === 'object' ? node.properties : {};
  const elementType = String(
    props.element_type ||
    props.type ||
    node?.type ||
    ''
  ).trim().toLowerCase();
  const semanticRole = String(props.semantic_role || '').trim().toLowerCase();
  const subType = String(props.sub_type || props.relationship_type || '').trim().toLowerCase();
  const relatedCount = Number(props.related_count || 0);

  if (semanticRole === 'relationship') return true;
  if (labels.includes('generalrelation') || elementType === 'generalrelation') return true;
  if (subType && /trace|satisf|allocat|realiz|ref/.test(subType) && relatedCount >= 1) return true;
  return false;
};

const normalizeNode = (node) => ({
  ...(node.properties || {}),
  elementId: node.elementId,
  labels: node.labels || ['Node'],
  label: node.labels?.[0] || 'Node',
  properties: node.properties || {},
  can_traverse: node.can_traverse,
});

const normalizeRelationship = (rel) => ({
  elementId: rel.elementId,
  source: rel.start ?? getLinkEndpointId(rel.source),
  target: rel.end ?? getLinkEndpointId(rel.target),
  type: normalizeRelationshipType(rel.type),
  properties: {
    ...(rel.properties || {}),
    raw_type: rel.type || rel.properties?.raw_type || '',
  },
});

const normalizeRawDataset = (payload) => {
  if (!payload) {
    return { nodes: [], links: [] };
  }

  if (Array.isArray(payload.nodes) && (Array.isArray(payload.relationships) || Array.isArray(payload.links))) {
    const rawRelationships = Array.isArray(payload.relationships) ? payload.relationships : payload.links;
    const nodes = payload.nodes
      .filter((node) => node?.elementId)
      .map(normalizeNode);

    const nodeIds = new Set(nodes.map((node) => node.elementId));
    const links = rawRelationships
      .filter((rel) => {
        const sourceId = rel?.start ?? getLinkEndpointId(rel?.source);
        const targetId = rel?.end ?? getLinkEndpointId(rel?.target);
        return rel?.elementId && nodeIds.has(sourceId) && nodeIds.has(targetId);
      })
      .map(normalizeRelationship);

    return deduplicateNodesAndLinks(nodes, links);
  }

  if (Array.isArray(payload.results)) {
    const nodesMap = new Map();
    const rawLinks = new Map();

    payload.results.forEach((record) => {
      const recordValues = Object.values(record || {});
      recordValues.forEach((value) => {
        if (value?.elementId && Array.isArray(value.labels)) {
          nodesMap.set(value.elementId, {
            ...(value.properties || {}),
            ...value,
            elementId: value.elementId,
            labels: value.labels || ['Node'],
            label: value.labels?.[0] || 'Node',
            properties: value.properties || {},
            can_traverse: value.can_traverse,
          });
        }

        if (Array.isArray(value)) {
          value.forEach((item) => {
            if (item?.elementId && Array.isArray(item.labels)) {
              nodesMap.set(item.elementId, {
                ...(item.properties || {}),
                ...item,
                elementId: item.elementId,
                labels: item.labels || ['Node'],
                label: item.labels?.[0] || 'Node',
                properties: item.properties || {},
                can_traverse: item.can_traverse,
              });
            }
            if (item?.source && item?.target) {
              rawLinks.set(item.elementId || `${getLinkEndpointId(item.source)}-${getLinkEndpointId(item.target)}-${item.type || 'REL'}`, {
                elementId: item.elementId || `${getLinkEndpointId(item.source)}-${getLinkEndpointId(item.target)}-${item.type || 'REL'}`,
                source: getLinkEndpointId(item.source),
                target: getLinkEndpointId(item.target),
                type: item.type,
                properties: item.properties || {},
              });
            }
          });
        }

        if (value?.source && value?.target) {
          rawLinks.set(value.elementId || `${getLinkEndpointId(value.source)}-${getLinkEndpointId(value.target)}-${value.type || 'REL'}`, {
            elementId: value.elementId || `${getLinkEndpointId(value.source)}-${getLinkEndpointId(value.target)}-${value.type || 'REL'}`,
            source: getLinkEndpointId(value.source),
            target: getLinkEndpointId(value.target),
            type: value.type,
            properties: value.properties || {},
          });
        }
      });
    });

    return deduplicateNodesAndLinks(Array.from(nodesMap.values()), Array.from(rawLinks.values()));
  }

  return { nodes: [], links: [] };
};

const collapseBridgeNodes = (nodes = [], links = [], options = {}) => {
  const { collapseMetadataWrappers = true, collapseRelationshipCarriers = true } = options;
  const nodeMap = new Map(nodes.map((node) => [node.elementId, node]));
  const shouldHideNode = (node) => (
    (collapseMetadataWrappers && isMetadataWrapperNode(node))
    || (collapseRelationshipCarriers && isRelationshipCarrierNode(node))
  );
  const visibleNodes = nodes.filter((node) => !shouldHideNode(node));
  const visibleIds = new Set(visibleNodes.map((node) => node.elementId));
  const incidentMap = new Map();

  links.forEach((link) => {
    const sourceId = getLinkEndpointId(link.source);
    const targetId = getLinkEndpointId(link.target);
    if (!sourceId || !targetId) return;
    if (!incidentMap.has(sourceId)) incidentMap.set(sourceId, []);
    if (!incidentMap.has(targetId)) incidentMap.set(targetId, []);
    incidentMap.get(sourceId).push(link);
    incidentMap.get(targetId).push(link);
  });

  const projectedLinks = [];
  const seenLinkKeys = new Set();

  const addProjectedLink = (link) => {
    const sourceId = getLinkEndpointId(link.source);
    const targetId = getLinkEndpointId(link.target);
    if (!sourceId || !targetId || sourceId === targetId) return;
    const key = `${sourceId}|${targetId}|${link.type}`;
    if (seenLinkKeys.has(key)) return;
    seenLinkKeys.add(key);
    projectedLinks.push({
      ...link,
      source: sourceId,
      target: targetId,
    });
  };

  links.forEach((link) => {
    const sourceId = getLinkEndpointId(link.source);
    const targetId = getLinkEndpointId(link.target);
    if (visibleIds.has(sourceId) && visibleIds.has(targetId)) {
      addProjectedLink(link);
    }
  });

  nodes
    .filter((node) => !visibleIds.has(node.elementId) && shouldHideNode(node))
    .forEach((hiddenNode) => {
      const incidentLinks = incidentMap.get(hiddenNode.elementId) || [];
      const visibleNeighbors = incidentLinks
        .map((link) => {
          const sourceId = getLinkEndpointId(link.source);
          const targetId = getLinkEndpointId(link.target);
          const otherId = sourceId === hiddenNode.elementId ? targetId : sourceId;
          return {
            node: nodeMap.get(otherId),
            nodeId: otherId,
            link,
          };
        })
        .filter((entry) => entry.nodeId && visibleIds.has(entry.nodeId));

      for (let index = 0; index < visibleNeighbors.length; index += 1) {
        for (let compare = index + 1; compare < visibleNeighbors.length; compare += 1) {
          const left = visibleNeighbors[index];
          const right = visibleNeighbors[compare];
          if (!left.nodeId || !right.nodeId || left.nodeId === right.nodeId) continue;

          const hiddenType = normalizeRelationshipType(
            hiddenNode?.properties?.element_type || hiddenNode?.labels?.[0] || 'TRACE'
          );
          addProjectedLink({
            elementId: `collapsed:${hiddenNode.elementId}:${left.nodeId}:${right.nodeId}:${left.link.type}:${right.link.type}`,
            source: left.nodeId,
            target: right.nodeId,
            type: hiddenType,
            properties: {
              collapsed: true,
              via_node_id: hiddenNode.elementId,
              via_node_type: hiddenType,
              left_rel_type: normalizeRelationshipType(left.link.type),
              right_rel_type: normalizeRelationshipType(right.link.type),
            },
          });
        }
      }
    });

  return deduplicateNodesAndLinks(visibleNodes, projectedLinks);
};

export const buildLinkSignature = (link) => {
  const sourceId = getLinkEndpointId(link?.source);
  const targetId = getLinkEndpointId(link?.target);
  if (!sourceId || !targetId) return null;
  const type = normalizeRelationshipType(link?.type || link?.properties?.raw_type || '');
  if (!type) return null;
  return `${sourceId}:${targetId}:${type}`;
};

export const deduplicateNodesAndLinks = (nodes = [], links = []) => {
  const nodeMap = new Map();
  nodes.forEach((node) => {
    if (!node?.elementId) return;
    const existing = nodeMap.get(node.elementId);
    if (!existing) {
      nodeMap.set(node.elementId, node);
      return;
    }
    nodeMap.set(node.elementId, {
      ...existing,
      ...node,
      labels: Array.from(new Set([...(existing.labels || []), ...(node.labels || [])])),
      properties: {
        ...(existing.properties || {}),
        ...(node.properties || {}),
      },
      can_traverse: existing.can_traverse === true || node.can_traverse === true
        ? true
        : (node.can_traverse ?? existing.can_traverse),
    });
  });

  const linkMap = new Map();
  links.forEach((link) => {
    const sourceId = getLinkEndpointId(link?.source);
    const targetId = getLinkEndpointId(link?.target);
    const key = buildLinkSignature(link);
    if (!link?.elementId || !sourceId || !targetId || !key) return;
    const type = normalizeRelationshipType(link?.type || link?.properties?.raw_type || '');
    const existing = linkMap.get(key);
    if (!existing) {
      linkMap.set(key, {
        ...link,
        source: sourceId,
        target: targetId,
        type,
        properties: {
          ...(link.properties || {}),
          raw_type: link?.properties?.raw_type || link?.type || '',
          merged_relation_count: 1,
        },
      });
      return;
    }

    existing.properties = {
      ...(existing.properties || {}),
      ...(link.properties || {}),
      raw_type: existing.properties?.raw_type || link?.properties?.raw_type || link?.type || '',
      merged_relation_count: (existing.properties?.merged_relation_count || 1) + 1,
    };
  });

  return {
    nodes: Array.from(nodeMap.values()),
    links: Array.from(linkMap.values()),
  };
};

export const mergeGraphData = (baseData = { nodes: [], links: [] }, incomingData = { nodes: [], links: [] }) => {
  const combinedNodes = [...(baseData.nodes || []), ...(incomingData.nodes || [])];
  const combinedLinks = [...(baseData.links || []), ...(incomingData.links || [])];
  return deduplicateNodesAndLinks(combinedNodes, combinedLinks);
};

export const getOneHopNeighborhood = (baseData = { nodes: [], links: [] }, rootNodeId) => {
  const normalizedRootId = String(rootNodeId || '').trim();
  if (!normalizedRootId) {
    return { nodes: [], links: [] };
  }

  const nodes = Array.isArray(baseData.nodes) ? baseData.nodes : [];
  const links = Array.isArray(baseData.links) ? baseData.links : [];
  const nodeMap = new Map(nodes.map((node) => [node?.elementId, node]).filter(([id]) => id));
  const rootNode = nodeMap.get(normalizedRootId);

  if (!rootNode) {
    return { nodes: [], links: [] };
  }

  const visibleNodeIds = new Set([normalizedRootId]);
  const visibleLinks = [];

  links.forEach((link) => {
    const sourceId = getLinkEndpointId(link?.source);
    const targetId = getLinkEndpointId(link?.target);
    if (sourceId === normalizedRootId || targetId === normalizedRootId) {
      visibleLinks.push(link);
      if (sourceId) visibleNodeIds.add(sourceId);
      if (targetId) visibleNodeIds.add(targetId);
    }
  });

  const visibleNodes = nodes.filter((node) => visibleNodeIds.has(node?.elementId));
  const connectedNodeIds = new Set(visibleNodes.map((node) => node.elementId));

  return deduplicateNodesAndLinks(
    visibleNodes,
    visibleLinks.filter((link) => {
      const sourceId = getLinkEndpointId(link?.source);
      const targetId = getLinkEndpointId(link?.target);
      return connectedNodeIds.has(sourceId) && connectedNodeIds.has(targetId);
    })
  );
};

export const removeExpandedSubgraph = (baseData = { nodes: [], links: [] }, removedNodeIds = [], removedLinkRefs = []) => {
  const removedNodes = new Set(removedNodeIds);
  const removedLinks = new Set(removedLinkRefs);
  return {
    nodes: (baseData.nodes || []).filter((node) => node?.elementId && !removedNodes.has(node.elementId)),
    links: (baseData.links || []).filter((link) => {
      const signature = buildLinkSignature(link);
      if (link?.elementId && removedLinks.has(link.elementId)) return false;
      if (signature && removedLinks.has(signature)) return false;
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      return !removedNodes.has(sourceId) && !removedNodes.has(targetId);
    }),
  };
};

export const validateConnectivity = (data = { nodes: [], links: [] }) => {
  const nodes = Array.isArray(data.nodes) ? data.nodes : [];
  const links = Array.isArray(data.links) ? data.links : [];
  const connectedIds = new Set();

  links.forEach((link) => {
    const sourceId = getLinkEndpointId(link.source);
    const targetId = getLinkEndpointId(link.target);
    if (sourceId) connectedIds.add(sourceId);
    if (targetId) connectedIds.add(targetId);
  });

  const orphanNodeIds = nodes
    .map((node) => node?.elementId)
    .filter((nodeId) => nodeId && !connectedIds.has(nodeId));

  const adjacency = new Map(nodes
    .map((node) => node?.elementId)
    .filter(Boolean)
    .map((nodeId) => [nodeId, new Set()]));
  links.forEach((link) => {
    const sourceId = getLinkEndpointId(link.source);
    const targetId = getLinkEndpointId(link.target);
    if (!adjacency.has(sourceId) || !adjacency.has(targetId)) return;
    adjacency.get(sourceId).add(targetId);
    adjacency.get(targetId).add(sourceId);
  });
  const remaining = new Set(adjacency.keys());
  const components = [];
  while (remaining.size > 0) {
    const start = remaining.values().next().value;
    const component = [];
    const pending = [start];
    remaining.delete(start);
    while (pending.length > 0) {
      const nodeId = pending.pop();
      component.push(nodeId);
      (adjacency.get(nodeId) || []).forEach((neighborId) => {
        if (!remaining.has(neighborId)) return;
        remaining.delete(neighborId);
        pending.push(neighborId);
      });
    }
    components.push(component);
  }

  return {
    isConnected: components.length <= 1,
    orphanNodeIds,
    componentCount: components.length,
    components,
  };
};

export const normalizeGraphDataset = (payload, options = {}) => {
  const { collapseHiddenBridges = false } = options;
  const normalizedRaw = normalizeRawDataset(payload);
  if (collapseHiddenBridges) {
    return collapseBridgeNodes(normalizedRaw.nodes, normalizedRaw.links, {
      collapseMetadataWrappers: true,
      collapseRelationshipCarriers: true,
    });
  }

  const containsRelationshipCarrier = normalizedRaw.nodes.some((node) => isRelationshipCarrierNode(node));
  if (containsRelationshipCarrier) {
    return collapseBridgeNodes(normalizedRaw.nodes, normalizedRaw.links, {
      collapseMetadataWrappers: false,
      collapseRelationshipCarriers: true,
    });
  }

  const nodes = normalizedRaw.nodes.filter((node) => node?.elementId && !isMetadataWrapperNode(node));
  const nodeIds = new Set(nodes.map((node) => node.elementId));
  const links = normalizedRaw.links.filter((link) => {
    const sourceId = getLinkEndpointId(link.source);
    const targetId = getLinkEndpointId(link.target);
    return link?.elementId && nodeIds.has(sourceId) && nodeIds.has(targetId);
  });

  return deduplicateNodesAndLinks(nodes, links);
};

export { getLinkEndpointId };
