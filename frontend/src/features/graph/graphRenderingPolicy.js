import { logger } from "../../utils/logger";
import { safeString } from "../../utils/safeAccess";
import { normalizeRelationshipType } from "../../utils/graphUtils";

const escapeHtml = (str) => {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

const isDevelopment = process.env.NODE_ENV === 'development';

const performanceLog = isDevelopment ? logger.render : () => {};

const performanceWarn = isDevelopment ? logger.warn : () => {};

const TCS_GRAPH_THEME = {
  ink: 'var(--ui-text)',
  inkSoft: 'var(--ui-muted)',
  inkMuted: 'var(--ui-muted)',
  border: 'var(--ui-border)',
  borderStrong: 'var(--ui-border)',
  surface: 'var(--ui-surface)',
  surfaceMuted: 'var(--ui-page)',
  surfaceAccent: 'var(--ui-surface-alt)',
  primary: 'var(--ui-primary)',
  primaryHover: 'var(--ui-primary-dark)',
  primarySoft: 'var(--ui-primary-soft)',
  success: '#486581',
  warm: '#8D6E63',
  alert: '#C05621',
  highlight: '#D9A441',
};

const LINK_COLOR = '#6B7C93';

const LINK_OPACITY = 0.72;

const LINK_STROKE_WIDTH = 1.35;

const NODE_RADIUS = 14;

const LINK_DISTANCE = 118;

const CHARGE_STRENGTH = -230;

const CENTER_FORCE_STRENGTH = 0.035;

const EXPAND_SYMBOL_SIZE = 10;

const EXPAND_CIRCLE_RADIUS = 13;

const ARROW_HEAD_LENGTH = 4.25;

const ARROW_HEAD_WIDTH = 2.2;

const ARROW_REF_X = NODE_RADIUS + 1.5;

const RELATIONSHIP_THEME = {
  generic: { color: LINK_COLOR, width: LINK_STROKE_WIDTH, dasharray: null, markerId: 'arrowhead-generic' },
  DOMAIN: { color: '#355C7D', width: 1.45, dasharray: null, markerId: 'arrowhead-domain' },
  RANGE: { color: '#8D6E63', width: 1.45, dasharray: null, markerId: 'arrowhead-range' },
  SUBCLASS_OF: { color: '#486581', width: 1.65, dasharray: '7 3', markerId: 'arrowhead-subclass' },
  SUBPROPERTY_OF: { color: '#52606D', width: 1.45, dasharray: '4 3', markerId: 'arrowhead-subproperty' },
  EQUIVALENT_CLASS: { color: '#D9A441', width: 1.55, dasharray: '3 2', markerId: 'arrowhead-equivalent' },
  DISJOINT_WITH: { color: '#C05621', width: 1.45, dasharray: '5 3', markerId: 'arrowhead-disjoint' },
  INVERSE_OF: { color: '#6B46C1', width: 1.45, dasharray: '4 2', markerId: 'arrowhead-inverse' },
  CLASS_RESTRICTION: { color: '#0F766E', width: 1.35, dasharray: '3 3', markerId: 'arrowhead-restriction' },
  ON_PROPERTY: { color: '#64748B', width: 1.25, dasharray: '2 3', markerId: 'arrowhead-on-property' },
  SOME_VALUES_FROM: { color: '#0E7490', width: 1.35, dasharray: null, markerId: 'arrowhead-some-values' },
  ALL_VALUES_FROM: { color: '#0369A1', width: 1.35, dasharray: null, markerId: 'arrowhead-all-values' },
  MASTER_REFERENCE: { color: '#B7791F', width: 1.35, dasharray: null, markerId: 'arrowhead-master-reference' },
  RELATED_REFERENCE: { color: '#D97706', width: 1.35, dasharray: null, markerId: 'arrowhead-related-reference' },
  PART_REFERENCE: { color: '#975A16', width: 1.35, dasharray: null, markerId: 'arrowhead-part-reference' },
  INSTANCE_REFERENCE: { color: '#2F855A', width: 1.35, dasharray: null, markerId: 'arrowhead-instance-reference' },
  PARENT_REFERENCE: { color: '#718096', width: 1.35, dasharray: '4 2', markerId: 'arrowhead-parent-reference' },
  SATISFIES: { color: '#B83280', width: 1.45, dasharray: '5 2', markerId: 'arrowhead-satisfies' },
  GENERAL_RELATION: { color: '#4A5568', width: 1.3, dasharray: '3 3', markerId: 'arrowhead-general-relation' },
  TRACE_LINK: { color: '#0F766E', width: 1.3, dasharray: '2 2', markerId: 'arrowhead-trace-link' },
};

const CHAR_MINUS      = '\u2212';

const CHAR_CHECK      = '\u2713';

const CHAR_CROSS      = '\u2717';

const resolveNodeType = (node) => {
  const props = node?.properties && typeof node.properties === 'object' && !Array.isArray(node.properties)
    ? node.properties
    : node || {};
  return (
    node?.entity_type ||
    props.entity_type ||
    node?.label ||
    node?.labels?.[0] ||
    'Node'
  );
};

const resolveNodeName = (node) => {
  const props = node?.properties && typeof node.properties === 'object' && !Array.isArray(node.properties)
    ? node.properties
    : node || {};
  const genericNames = new Set(['node', 'datanode', 'entity', 'graphnode', 'unknown', 'item']);
  const candidates = [
    node?.name,
    props.name,
    node?.title,
    props.title,
    node?.code,
    props.code,
    props.key,
    props.uid,
    props.identifier,
    props.instance_id,
    props.instanceId,
    props.abbreviation,
    props.part_number,
    props.product_name,
    props.project_name,
    props.external_id,
    props.idref,
    props.href,
    props.label,
    node?.label,
    node?.labels?.[0],
    props.class_label,
    props.class_name,
    props.concept_type,
    props.original_type,
    props.owl_class,
    props.rdf_type,
    props.entity_type,
    node?.entity_type,
  ];

  for (const candidate of candidates) {
    const text = safeString(candidate, '').trim();
    if (!text) continue;
    if (genericNames.has(text.toLowerCase())) continue;
    return text;
  }

  const fallback = props.original_type || props.class_label || props.class_name || props.concept_type || props.entity_type || node?.entity_type;
  return safeString(fallback, 'Unknown');
};

const getRelationshipVisual = (relationshipType) => {
  const key = normalizeRelationshipType(relationshipType);
  return RELATIONSHIP_THEME[key] || RELATIONSHIP_THEME.generic;
};

const getVisibleRelationshipStrokeWidth = (relationshipType, nodeCount, linkCount) => {
  const baseWidth = Number(getRelationshipVisual(relationshipType).width || LINK_STROKE_WIDTH);
  const densityAdjusted = nodeCount > 120 || linkCount > 160
    ? Math.min(baseWidth, 1.75)
    : baseWidth;
  return Math.min(3, Math.max(densityAdjusted, 1.25));
};

const getVisibleRelationshipOpacity = (nodeCount, linkCount) => {
  if (nodeCount > 120 || linkCount > 160) return 0.86;
  return Math.max(LINK_OPACITY, 0.78);
};

const RELATIONSHIP_DISPLAY_NAMES = {
  MASTER_REFERENCE: 'Master Reference',
  MASTERREF: 'Master Reference',
  MASTER_REF: 'Master Reference',
  RELATED_REFERENCE: 'Related Reference',
  RELATEDREFS: 'Related Reference',
  RELATEDREF: 'Related Reference',
  PART_REFERENCE: 'Part Reference',
  PART_REF: 'Part Reference',
  PARTREF: 'Part Reference',
  OCCURRENCE_REFERENCE: 'Occurrence Reference',
  OCCURRENCE_REF: 'Occurrence Reference',
  OCCURRENCEREFS: 'Occurrence References',
  INSTANCE_REFERENCE: 'Instance Reference',
  INSTANCEDREF: 'Instance Reference',
  INSTANCEREFS: 'Instance References',
  HAS_CHILD_INSTANCE: 'Contains Instance',
  HAS_PARENT_INSTANCE: 'Contained In Instance',
  PARENT_REFERENCE: 'Parent Reference',
  PARENTREF: 'Parent Reference',
  SATISFIES: 'Satisfies',
  SEG0SATISFY: 'Satisfies',
  GENERAL_RELATION: 'General Relation',
  GENERALRELATION: 'General Relation',
  TRACE_LINK: 'Trace Link',
  TRACE: 'Trace Link',
};

const getRelationshipDisplayName = (relationship) => {
  const rawType = String(
    typeof relationship === 'string'
      ? relationship
      : (relationship?.type || relationship?.properties?.type || '')
  ).trim();
  const normalized = normalizeRelationshipType(rawType);
  if (relationship?.properties?.collapsed) return 'Trace Link';
  return RELATIONSHIP_DISPLAY_NAMES[normalized] || RELATIONSHIP_DISPLAY_NAMES[rawType] || rawType || 'Relationship';
};

const getNodeCollisionRadius = (node, showLabels) => {
  const base = NODE_RADIUS + 14;
  if (!showLabels) return base;
  const displayLength = Math.min(resolveNodeName(node).length, 28);
  return base + Math.max(16, Math.round(displayLength * 3.0));
};

const getAdaptiveLinkDistance = (relationshipType, nodeCount, linkCount) => {
  const base = relationshipType === 'SUBCLASS_OF'
    ? 170
    : (relationshipType === 'DOMAIN' || relationshipType === 'RANGE' ? 150 : LINK_DISTANCE);
  if (nodeCount > 140 || linkCount > 260) return Math.max(96, base - 18);
  if (nodeCount > 70 || linkCount > 140) return base + 18;
  return base + 28;
};

const getAdaptiveChargeStrength = (nodeCount) => {
  if (nodeCount > 180) return -220;
  if (nodeCount > 90) return -245;
  if (nodeCount > 40) return CHARGE_STRENGTH;
  return -280;
};

const getNodeSemanticFamily = (nodeLike) => {
  const label = resolveNodeType(nodeLike);
  const props = nodeLike?.properties && typeof nodeLike.properties === 'object' && !Array.isArray(nodeLike.properties)
    ? nodeLike.properties
    : nodeLike || {};
  const normalized = `${label || ''} ${props.entity_type || ''} ${props.semantic_role || ''}`.toLowerCase();
  if (normalized.includes('ontologyclass') || normalized.includes(' class')) return 'Classes';
  if (normalized.includes('objectproperty') || normalized.includes('property')) return 'Properties';
  if (normalized.includes('datatypeproperty') || normalized.includes('datatype')) return 'Data Types';
  if (normalized.includes('requirement') || normalized.includes('specification')) return 'Requirements';
  if (normalized.includes('document') || normalized.includes('view') || normalized.includes('package')) return 'Documents';
  if (normalized.includes('part') || normalized.includes('product') || normalized.includes('assembly') || normalized.includes('bom')) return 'Products';
  if (normalized.includes('relation') || normalized.includes('trace') || normalized.includes('connection')) return 'Relations';
  if (normalized.includes('instance') || normalized.includes('individual') || normalized.includes('resource')) return 'Instances';
  return 'Other';
};

const getClusterTarget = (family, width, height) => {
  const positions = {
    Classes: [0.28, 0.24],
    Properties: [0.7, 0.24],
    'Data Types': [0.84, 0.46],
    Requirements: [0.24, 0.72],
    Documents: [0.52, 0.18],
    Products: [0.62, 0.72],
    Relations: [0.18, 0.48],
    Instances: [0.82, 0.72],
    Other: [0.5, 0.5],
  };
  const [xFactor, yFactor] = positions[family] || positions.Other;
  return { x: width * xFactor, y: height * yFactor };
};

export { RELATIONSHIP_THEME, LINK_COLOR, LINK_STROKE_WIDTH, ARROW_HEAD_WIDTH, ARROW_HEAD_LENGTH, ARROW_REF_X, NODE_RADIUS, TCS_GRAPH_THEME, getAdaptiveLinkDistance, LINK_DISTANCE, getAdaptiveChargeStrength, CHARGE_STRENGTH, CENTER_FORCE_STRENGTH, getClusterTarget, getNodeSemanticFamily, resolveNodeType, getNodeCollisionRadius, resolveNodeName, getRelationshipVisual, getVisibleRelationshipOpacity, LINK_OPACITY, getVisibleRelationshipStrokeWidth, getRelationshipDisplayName, RELATIONSHIP_DISPLAY_NAMES, escapeHtml, CHAR_CHECK, CHAR_CROSS, EXPAND_CIRCLE_RADIUS, EXPAND_SYMBOL_SIZE, CHAR_MINUS, performanceLog, isDevelopment, performanceWarn };
