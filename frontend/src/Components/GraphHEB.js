import React, { useEffect, useRef, useState, useCallback, useMemo, startTransition } from 'react';
import * as d3 from 'd3';
import '../CSS/GraphHEB.css';
import { useSchema } from '../SchemaContext';
import { useOntologies } from '../contexts/OntologyContext';
import { logger } from '../utils/logger';
import { safeGet, safeString } from '../utils/safeAccess';
import {
  deduplicateNodesAndLinks,
  getOneHopNeighborhood,
  mergeGraphData,
  isMetadataWrapperNode,
  normalizeGraphDataset as normalizeGraphDatasetShared,
  normalizeRelationshipType,
  normalizeSearchTerm,
  removeExpandedSubgraph,
  validateConnectivity,
} from '../utils/graphUtils';
import { buildUrl, replaceParams, API } from '../config';
import { apiClient } from '../services/apiClient';
import { graphApi } from '../services/graphApi';
import { buildTooltipHeader } from './tooltipBuilder';
import GraphExplorerToolbar from './GraphExplorerToolbar';

// Security: HTML-escape utility for tooltip interpolation
const escapeHtml = (str) => {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

// ──── DEVELOPER CONFIG: Node Display Label ────────────────────────────────
//
// DISPLAY_NAME_PROPERTY  — priority-ordered list of node properties to try.
//   The first property found on a node is used as the display name.
//   Set to [] (empty array) to rely solely on the Neo4j label.
const DISPLAY_NAME_PROPERTY = ['name', 'title', 'code', 'key', 'abbreviation', 'entity_type'];
//
// DISPLAY_MODE  — controls what is shown in the node label.
//   'both-label-first'  → "Label - PropertyValue"   (default)
//   'both-prop-first'   → "PropertyValue (Label)"
//   'label-only'        → "Label"
//   'property-only'     → "PropertyValue"
const DISPLAY_MODE = 'both-label-first';
// ───────────────────────────────────────────────────────────────────────────

// Define constants for graph tuning values.
// These improve readability and maintainability
const HIGHLIGHT_AUTO_CLEAR_MS = 15000;        // 15 seconds - clear highlight after timeout
const ENTITY_EXTRACTION_DELAY_MS = 500;       // 500ms - allow text selection to settle
const TREE_ROW_HEIGHT_PX = 40;                // 40px - height of each tree row
const TREE_INDENT_WIDTH_PX = 30;              // 30px - indent per tree level
const TREE_LAYOUT_PADDING_PX = 40;            // 40px - padding from edges
const TREE_DEFAULT_HEIGHT_PX = 600;           // 600px - default tree container height
const TREE_MIN_CONTENT_HEIGHT_PX = 560;       // 560px - minimum height before scrolling
const DEFAULT_GRAPH_OVERVIEW_LIMIT = 900;
const DEFAULT_ONTOLOGY_VIEW_LIMIT = 200;
// Helper: resolve the first matching property from DISPLAY_NAME_PROPERTY list
const resolveDisplayProp = (props) => {
  if (!props || !DISPLAY_NAME_PROPERTY || DISPLAY_NAME_PROPERTY.length === 0) return null;
  for (const key of DISPLAY_NAME_PROPERTY) {
    const value = safeGet(props, key, null);
    if (value != null) return String(value);
  }
  return null;
};

// Helper: format a display string from a Neo4j label and a property value
const formatNodeDisplay = (label, propValue) => {
  const safeLabel = safeString(label, null);
  const safeProp = safeString(propValue, null);

  switch (DISPLAY_MODE) {
    case 'label-only':
      return safeLabel || safeProp || 'Unknown';
    case 'property-only':
      return safeProp || safeLabel || 'Unknown';
    case 'both-prop-first':
      if (!safeProp) return safeLabel || 'Unknown';
      if (!safeLabel) return safeProp;
      return `${safeProp} (${safeLabel})`;
    case 'both-label-first':
    default:
      if (!safeProp) return safeLabel || 'Unknown';
      if (!safeLabel) return safeProp;
      return `${safeLabel} - ${safeProp}`;
  }
};

const resolveOntologySearchPrefix = (ontologyValue) => {
  if (!ontologyValue || ontologyValue === 'ALL' || ontologyValue === 'step' || ontologyValue === 'mbse_instances') {
    return '';
  }
  if (ontologyValue.endsWith('_instances')) {
    return ontologyValue.replace(/_instances$/, '');
  }
  return ontologyValue;
};

// Performance: Disable excessive console logging in production
const isDevelopment = process.env.NODE_ENV === 'development';
const performanceLog = isDevelopment ? logger.render : () => {};
const performanceWarn = isDevelopment ? logger.warn : () => {};

// Performance: (legacy) caching removed — unused in current code

// ── RecPanelResult: recommendation slide-in panel results renderer ────────────
const _PILL = (c) => ({ display: 'inline-block', padding: '2px 8px', borderRadius: '10px', fontSize: '11px', fontWeight: 600, background: c, color: '#fff', marginRight: '4px', marginBottom: '3px' });
const _ROW  = { padding: '6px 0', borderBottom: '1px solid #f0f0f0', fontSize: '12px' };

function RecPanelResult({ service, data, setRecPanel, setActiveTab }) {
  const viewBtn = (names) => (
    <button
      onClick={() => { window.dispatchEvent(new CustomEvent('dt-highlight-nodes', { detail: { names } })); setRecPanel(p => ({ ...p, open: false })); }}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 10px', border: '1px solid #004B87', borderRadius: '5px', background: '#EBF5FB', color: '#004B87', fontSize: '11px', fontWeight: 600, cursor: 'pointer', marginTop: '8px' }}
    >
      \uD83D\uDD0E Highlight in Graph
    </button>
  );

  if (service === 'change-impact') {
    const ce = data.change_entity;
    if (!ce) return <div style={{ color: '#7f8c8d' }}>No entity found</div>;
    const allNames = [ce.name, ...(data.impacted_parts || []).map(p => p.name), ...(data.assembly_impact || []).map(a => a.assembly_name)].filter(Boolean);
    return (
      <div>
        <div style={{ fontWeight: 700, marginBottom: '8px' }}>Impact Score: <span style={{ color: data.impact_score > 50 ? '#e74c3c' : '#27ae60' }}>{data.impact_score}</span>/100</div>
        {data.impacted_parts?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Impacted Parts ({data.impacted_parts.length})</strong>{data.impacted_parts.slice(0, 8).map((p, i) => <div key={i} style={_ROW}><span style={_PILL('#3498db')}>{p.source_tag || '?'}</span> {p.name}</div>)}</div>}
        {data.assembly_impact?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Assemblies ({data.assembly_impact.length})</strong>{data.assembly_impact.slice(0, 6).map((a, i) => <div key={i} style={_ROW}>{a.assembly_name} <em style={{ color: '#999' }}>depth {a.depth}</em></div>)}</div>}
        {data.process_impacts?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Processes ({data.process_impacts.length})</strong></div>}
        {data.realization_chain?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Realization ({data.realization_chain.length})</strong></div>}
        {allNames.length > 0 && viewBtn(allNames)}
      </div>
    );
  }
  if (service === 'similar-parts') {
    if (!data.source_part) return <div style={{ color: '#7f8c8d' }}>Not found</div>;
    const allNames = [data.source_part.name, ...(data.similar_parts || []).map(p => p.name)].filter(Boolean);
    return (
      <div>
        <div style={{ fontWeight: 700, marginBottom: '8px' }}>{data.similar_parts?.length || 0} similar parts</div>
        {(data.similar_parts || []).slice(0, 10).map((p, i) => (
          <div key={i} style={_ROW}>
            <strong>{p.name}</strong> \u2014 <span style={{ color: '#004B87', fontWeight: 600 }}>{p.similarity_score}</span>
            {p.shared_assembly && <span style={_PILL('#27ae60')}>Assembly</span>}
            {p.traceability_link && <span style={_PILL('#e67e22')}>{p.traceability_link}</span>}
          </div>
        ))}
        {allNames.length > 1 && viewBtn(allNames)}
      </div>
    );
  }
  if (service === 'manufacturing') {
    if (!data.part) return <div style={{ color: '#7f8c8d' }}>Not found</div>;
    const allNames = [data.part.name, ...(data.direct_processes || []).map(p => p.process_name), ...(data.process_instances || []).map(p => p.name)].filter(Boolean);
    return (
      <div>
        {data.direct_processes?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Direct ({data.direct_processes.length})</strong>{data.direct_processes.slice(0, 6).map((p, i) => <div key={i} style={_ROW}><span style={_PILL('#004B87')}>{p.source_tag || '?'}</span> {p.process_name}</div>)}</div>}
        {data.process_instances?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Instances ({data.process_instances.length})</strong>{data.process_instances.slice(0, 6).map((p, i) => <div key={i} style={_ROW}>{p.name}</div>)}</div>}
        {data.related_part_processes?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Related ({data.related_part_processes.length})</strong></div>}
        {allNames.length > 1 && viewBtn(allNames)}
      </div>
    );
  }
  return null;
}
// ───────────────────────────────────────────────────────────────────────────────

// Define constants for D3 parameters and styling
const TCS_GRAPH_THEME = {
  ink: '#1F2933',
  inkSoft: '#52606D',
  inkMuted: '#7B8794',
  border: '#D9E2EC',
  borderStrong: '#BCCCDC',
  surface: '#FFFFFF',
  surfaceMuted: '#F7F9FB',
  surfaceAccent: '#EEF3F8',
  primary: '#1F3D63',
  primaryHover: '#274C77',
  primarySoft: '#EAF1F7',
  success: '#486581',
  warm: '#8D6E63',
  alert: '#C05621',
  highlight: '#D9A441',
};

const LINK_COLOR = '#6B7C93';        // TCS-inspired muted steel link
const LINK_OPACITY = 0.72;
const LINK_STROKE_WIDTH = 1.35;
const NODE_RADIUS = 14;
const LINK_DISTANCE = 100;
const CHARGE_STRENGTH = -150;        // ✅ Reduced from -300 to prevent node separation
const ALPHA_TARGET_DRAG = 0.3;
const ALPHA_TARGET_END = 0;

// NEW CONSTANTS FOR CENTERING AND VIEWPORT
const CENTER_FORCE_STRENGTH = 0.05;
const VIEWPORT_PADDING = 50;

// NEW CONSTANTS FOR EXPAND/COLLAPSE
const EXPAND_SYMBOL_SIZE = 10;
const EXPAND_CIRCLE_RADIUS = 13;

// NEW CONSTANTS FOR ARROWHEADS
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

const CHAR_MINUS      = '\u2212';     // −   minus sign
const CHAR_BULLET     = '\u2022';     // •   bullet
const CHAR_CHECK      = '\u2713';     // ✓   check mark
const CHAR_CROSS      = '\u2717';     // ✗   ballot x
// ───────────────────────────────────────────────────────────────────────────

const ENTITY_COLOR_SWATCH = [
  '#1F3D63', '#355C7D', '#486581', '#0F766E', '#8D6E63', '#C05621',
  '#6B46C1', '#0E7490', '#A16207', '#BE185D', '#3E4C59', '#0F4C5C',
];

const hashText = (value) => {
  const text = String(value || '');
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash) + text.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
};

const resolveNodeColorKey = (nodeLike) => {
  if (typeof nodeLike === 'string') return nodeLike;
  const props = nodeLike?.properties && typeof nodeLike.properties === 'object' && !Array.isArray(nodeLike.properties)
    ? nodeLike.properties
    : nodeLike || {};
  return safeString(
    props.sub_type ||
    props.subtype ||
    props.entity_subtype ||
    props.entitySubtype ||
    props.subclass ||
    props.sub_class ||
    props.subclass_of ||
    props.subClassOf ||
    props.parent_class ||
    props.parentClass ||
    props.super_class ||
    props.superClass ||
    props.owl_class ||
    props.owlClass ||
    props.rdf_type ||
    props.rdfType ||
    props.class_label ||
    props.entity_type ||
    props.original_type ||
    props.concept_type ||
    props.class_name ||
    props.type ||
    nodeLike?.entity_type ||
    nodeLike?.label ||
    nodeLike?.labels?.[0] ||
    'Node',
    'Node'
  );
};

// Performance: Debounce hook for search optimization
const useDebounce = (value, delay) => {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
};

// Performance: Memoized node search function
const createNodeSearchFunction = () => {
  const normalizeRawSearch = (value) => String(value || '').trim().toLowerCase();

  const scoreFieldMatch = (value, lowerSearchTerm, rawSearchTerm) => {
    if (value == null) return 0;
    const text = String(value).trim().toLowerCase();
    if (!text) return 0;
    const wildcardPrefix = rawSearchTerm.endsWith('*')
      ? rawSearchTerm.replace(/\*+$/g, '')
      : '';

    if (wildcardPrefix) {
      if (text === wildcardPrefix) return 1000;
      if (text.startsWith(wildcardPrefix)) return 900;
      if (text.includes(wildcardPrefix)) return 650;
    }

    if (text === lowerSearchTerm) return 1000;
    if (text.startsWith(lowerSearchTerm)) return 800;
    if (text.includes(lowerSearchTerm)) return 500;
    return 0;
  };

  const containsSearchTerm = (value, lowerSearchTerm, rawSearchTerm, depth = 0) => {
    if (value == null || depth > 3) return false;

    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      const text = String(value).toLowerCase();
      if (text.includes(lowerSearchTerm)) return true;
      if (rawSearchTerm.endsWith('*')) {
        return text.includes(rawSearchTerm.replace(/\*+$/g, ''));
      }
      return false;
    }

    if (Array.isArray(value)) {
      return value.some((item) => containsSearchTerm(item, lowerSearchTerm, rawSearchTerm, depth + 1));
    }

    if (typeof value === 'object') {
      return Object.values(value).some((item) => containsSearchTerm(item, lowerSearchTerm, rawSearchTerm, depth + 1));
    }

    return false;
  };

  return (nodes, searchTerm) => {
    const rawSearchTerm = normalizeRawSearch(searchTerm);
    const lowerSearchTerm = normalizeSearchTerm(searchTerm);
    if (!lowerSearchTerm || lowerSearchTerm.length < 2) return nodes;
    return nodes
      .map((node) => {
        let score = 0;

        if (isMetadataWrapperNode(node)) {
          score -= 250;
        }

        const props = node?.properties && typeof node.properties === 'object' && !Array.isArray(node.properties)
          ? node.properties
          : node || {};

        const exactFields = [
          node?.elementId,
          node?.id,
          node?.name,
          node?.title,
          node?.code,
          props.id,
          props.uid,
          props.name,
          props.title,
          props.code,
          props.key,
          props.identifier,
          props.catalogue_id,
          props.requirement_id,
          props.requirement_ref,
          props.uuid,
          props.part_number,
          props.product_name,
          props.project_name,
          props.instance_id,
          props.instanceId,
          props.external_id,
          props.idref,
          props.href,
        ];

        exactFields.forEach((field) => {
          score = Math.max(score, scoreFieldMatch(field, lowerSearchTerm, rawSearchTerm));
        });

        if (node?.properties) {
          const propText = JSON.stringify(node.properties).toLowerCase();
          if (propText.includes(lowerSearchTerm)) {
            score = Math.max(score, 200);
          }
        }

        if (containsSearchTerm(node, lowerSearchTerm, rawSearchTerm)) {
          score = Math.max(score, 100);
        }

        return { node, score };
      })
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score)
      .map(({ node }) => node);
  };
};

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

const getNodeSemanticHints = (node) => {
  const props = node?.properties && typeof node.properties === 'object' && !Array.isArray(node.properties)
    ? node.properties
    : node || {};
  const labels = Array.isArray(node?.labels) ? node.labels.map(label => String(label || '').toLowerCase()) : [];
  const tokens = [
    node?.entity_type,
    props.entity_type,
    node?.label,
    labels[0],
    props.type,
    props.node_type,
    props.element_type,
    props.part_type,
    props.change_type,
    props.original_type,
  ]
    .filter(Boolean)
    .map(value => String(value).toLowerCase());

  const combined = `${labels.join(' ')} ${tokens.join(' ')}`.trim();
  return {
    isPartLike:
      combined.includes('part') ||
      combined.includes('product') ||
      combined.includes('assembly') ||
      combined.includes('component'),
    isChangeLike:
      combined.includes('change') ||
      combined.includes('ecn') ||
      combined.includes('eco') ||
      combined.includes('ecr') ||
      combined.includes('notice') ||
      combined.includes('request'),
  };
};

const isSchemaTerminalNode = (node) => {
  const labels = Array.isArray(node?.labels) ? node.labels.map((label) => String(label || '')) : [];
  return labels.some((label) => (
    label === 'OntologyClass' ||
    label === 'Class' ||
    label === 'ObjectProperty' ||
    label === 'DatatypeProperty' ||
    label === 'Restriction' ||
    label === 'OntologyRestriction' ||
    label === 'Datatype'
  ));
};

const isIndividualTraversalNode = (node) => {
  const labels = Array.isArray(node?.labels) ? node.labels.map((label) => String(label || '').toLowerCase()) : [];
  return labels.includes('individual');
};

const hasNodeLabel = (node, expected) => {
  const labels = Array.isArray(node?.labels) ? node.labels : [];
  return labels.some((label) => String(label || '').toLowerCase() === String(expected || '').toLowerCase());
};

const isRequirementContextNode = (node) => {
  const props = node?.properties && typeof node.properties === 'object' && !Array.isArray(node.properties)
    ? node.properties
    : node || {};
  return (
    hasNodeLabel(node, 'Requirement')
    || hasNodeLabel(node, 'RequirementRevision')
    || hasNodeLabel(node, 'GeneralRelation')
    || Boolean(props.catalogue_id)
    || Boolean(props.requirement_id)
    || Boolean(props.requirement_ref)
  );
};

const getRelationshipVisual = (relationshipType) => {
  const key = normalizeRelationshipType(relationshipType);
  return RELATIONSHIP_THEME[key] || RELATIONSHIP_THEME.generic;
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

const getLinkEndpointId = (endpoint) => {
  if (!endpoint) return null;
  if (typeof endpoint === 'object') {
    return endpoint.elementId || endpoint.id || endpoint.identity || endpoint._id || null;
  }
  return endpoint;
};

const getNodeCollisionRadius = (node, showLabels) => {
  const base = NODE_RADIUS + 10;
  if (!showLabels) return base;
  const displayLength = Math.min(resolveNodeName(node).length, 22);
  return base + Math.max(10, Math.round(displayLength * 2.1));
};

export const normalizeGraphDataset = (payload, options) => normalizeGraphDatasetShared(payload, options);

const GraphHEB = ({ setData, setSearchResults, showChat, toggleChat, setActiveTab, setVisibleRelationships, chatResults }) => {
  const svgRef = useRef();
  const tooltipRef = useRef();
  const [tooltipDocked, setTooltipDocked] = useState(true);
  const tooltipDockedRef = useRef(tooltipDocked);
  useEffect(() => { tooltipDockedRef.current = tooltipDocked; }, [tooltipDocked]);

  const simulationRef = useRef(null);
  const gRef = useRef(null); // Ref for the main D3 group element
  const zoomBehaviorRef = useRef(null);
  const tickFrameRef = useRef(null);
  const activeTooltipNodeRef = useRef(null); // Track which node/link the tooltip is showing for
  const timeoutsRef = useRef(new Set()); // Track active timeouts for cleanup
  const lastCenteredSearchRef = useRef('');
  const previousSearchQueryRef = useRef('');
  const userInteractedWithGraphRef = useRef(false);

  // Helper: build close button HTML for tooltips
  const tooltipCloseBtn = `<button class="dt-tooltip-close" style="position:absolute;top:6px;right:8px;background:none;border:none;color:white;font-size:16px;cursor:pointer;line-height:1;padding:0 2px;opacity:0.85;">&times;</button>`;

  // Helper: attach close handler to tooltip element (clears active tooltip state)
  const applyTooltipCloseHandler = (tooltipEl) => {
    if (!tooltipEl) return;
    const closeBtn = tooltipEl.querySelector('.dt-tooltip-close');
    if (!closeBtn) return;
    // Remove previous listener if present
    closeBtn.replaceWith(closeBtn.cloneNode(true));
    const newBtn = tooltipEl.querySelector('.dt-tooltip-close');
    newBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      tooltipEl.style.opacity = '0';
      tooltipEl.style.display = 'none';
      tooltipEl.style.pointerEvents = 'none';
      activeTooltipNodeRef.current = null;
    });
  };

  const wireTooltipRecButtons = (tooltipEl, onAction) => {
    if (!tooltipEl) return;
    tooltipEl.querySelectorAll('.dt-rec-btn').forEach((btn) => {
      btn.onclick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const service = btn.getAttribute('data-rec-service');
        const nodeName = btn.getAttribute('data-rec-node') || '';
        const nodeId = btn.getAttribute('data-rec-node-id') || '';
        const ontologyPrefix = btn.getAttribute('data-rec-prefix') || '';
        const ontologyId = btn.getAttribute('data-rec-ontology-id') || '';
        if (typeof onAction === 'function' && service) {
          onAction(service, nodeName, { nodeId, ontologyPrefix, ontologyId });
        }
      };
    });
  };

  // Helper: hide both tooltips
  const hideAllTooltips = useCallback(() => {
    if (tooltipRef.current) {
      tooltipRef.current.style.opacity = '0';
      tooltipRef.current.style.display = 'none';
      tooltipRef.current.style.pointerEvents = 'none';
    }
    activeTooltipNodeRef.current = null;
  }, []);

  // Reposition tooltip on resize/scroll to keep it anchored to SVG canvas
  const repositionTooltip = useCallback(() => {
    const el = tooltipRef.current;
    const svg = svgRef.current;
    if (!el || !svg) return;
    const svgRect = svg.getBoundingClientRect();
    const parentEl = svg.parentElement || svg.offsetParent;
    if (!parentEl) return;
    const parentRect = parentEl.getBoundingClientRect();
    const panelWidth = 360;
    const panelHeight = Math.max(120, svgRect.height);
    // Dock tooltip to right side of the SVG canvas
    let panelTop = Math.max(0, Math.round(svgRect.top - parentRect.top));
    let panelLeft = Math.max(0, Math.round(svgRect.right - parentRect.left - panelWidth));
    if (svgRect.width < panelWidth) panelLeft = Math.max(0, Math.round(svgRect.left - parentRect.left));
    el.style.position = 'absolute';
    el.style.top = panelTop + 'px';
    el.style.left = panelLeft + 'px';
    el.style.right = 'auto';
    el.style.width = panelWidth + 'px';
    el.style.maxHeight = Math.min(panelHeight, window.innerHeight - 40) + 'px';
    el.style.overflowY = 'auto';
  }, []);

  useEffect(() => {
    window.addEventListener('resize', repositionTooltip);
    window.addEventListener('scroll', repositionTooltip, true);
    repositionTooltip();
    return () => {
      window.removeEventListener('resize', repositionTooltip);
      window.removeEventListener('scroll', repositionTooltip, true);
    };
  }, [repositionTooltip]);

  // Make tooltip element draggable within parent bounds (pointer events)
  const makeTooltipDraggable = useCallback((tooltipEl) => {
    if (!tooltipEl || !svgRef.current) return;
    const parentEl = svgRef.current.parentElement || svgRef.current.offsetParent;
    if (!parentEl) return;

    let dragging = false;
    let startX = 0;
    let startY = 0;
    let startLeft = 0;
    let startTop = 0;
    const panelWidth = tooltipEl.offsetWidth || 340;
    const panelHeight = tooltipEl.offsetHeight || svgRef.current.getBoundingClientRect().height;

    const onPointerMove = (ev) => {
      if (!dragging) return;
      const clientX = ev.clientX !== undefined ? ev.clientX : (ev.touches && ev.touches[0]?.clientX);
      const clientY = ev.clientY !== undefined ? ev.clientY : (ev.touches && ev.touches[0]?.clientY);
      const parentRect = parentEl.getBoundingClientRect();
      let dx = clientX - startX;
      let dy = clientY - startY;
      let newLeft = startLeft + dx;
      let newTop = startTop + dy;
      // clamp
      newLeft = Math.max(0, Math.min(newLeft, parentRect.width - panelWidth));
      newTop = Math.max(0, Math.min(newTop, parentRect.height - panelHeight));
      tooltipEl.style.left = `${Math.round(newLeft)}px`;
      tooltipEl.style.top = `${Math.round(newTop)}px`;
    };

    const onPointerUp = () => {
      dragging = false;
      document.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('pointerup', onPointerUp);
    };

    const onPointerDown = (ev) => {
      ev.preventDefault();
      dragging = true;
      const clientX = ev.clientX !== undefined ? ev.clientX : (ev.touches && ev.touches[0]?.clientX);
      const clientY = ev.clientY !== undefined ? ev.clientY : (ev.touches && ev.touches[0]?.clientY);
      startX = clientX;
      startY = clientY;
      const rect = tooltipEl.getBoundingClientRect();
      const parentRect = parentEl.getBoundingClientRect();
      startLeft = rect.left - parentRect.left;
      startTop = rect.top - parentRect.top;
      document.addEventListener('pointermove', onPointerMove);
      document.addEventListener('pointerup', onPointerUp);
    };

    // Attach drag to handle if present, otherwise to whole panel
    const handleEl = tooltipEl.querySelector('.dt-tooltip-handle') || tooltipEl;
    tooltipEl.style.touchAction = 'none';
    tooltipEl.setAttribute('draggable', 'true');
    // remove previous handler if any
    if (tooltipEl._dt_onPointerDown && handleEl) handleEl.removeEventListener('pointerdown', tooltipEl._dt_onPointerDown);
    tooltipEl._dt_onPointerDown = onPointerDown;
    handleEl.addEventListener('pointerdown', onPointerDown);
  }, []);

  const openTooltipRecommendation = useCallback((service, nodeName, context = {}) => {
    const normalizedName = String(nodeName || '').trim();
    if (!service) return;
    if (!normalizedName) {
      setRecPanel({
        open: true,
        service,
        nodeName: 'Unavailable',
        loading: false,
        result: null,
        error: 'This tooltip item does not expose a usable node name for recommendation analysis.',
      });
      hideAllTooltips();
      return;
    }

    setRecPanel({ open: true, service, nodeName: normalizedName, loading: true, result: null, error: '' });
    hideAllTooltips();

    const endpoint = service === 'change-impact'
      ? '/recommendations/change-impact'
      : service === 'similar-parts'
      ? '/recommendations/similar-parts'
      : '/recommendations/manufacturing';
    const scope = {
      ...(context.ontologyPrefix ? { prefix: context.ontologyPrefix } : {}),
      ...(context.ontologyId ? { ontology_id: context.ontologyId } : {}),
      ...(context.nodeId ? { node_id: context.nodeId } : {}),
    };
    const body = service === 'change-impact'
      ? { change_name: normalizedName, node_id: context.nodeId, scope }
      : service === 'similar-parts'
      ? { part_name: normalizedName, top_n: 10, node_id: context.nodeId, scope }
      : { part_name: normalizedName, node_id: context.nodeId, scope };

    apiClient.post(buildUrl(endpoint), body)
      .then(resp => {
        const payload = resp.data;
        const hasVisibleResult = payload && (
          (Array.isArray(payload) && payload.length > 0) ||
          (typeof payload === 'object' && Object.keys(payload).length > 0)
        );
        setRecPanel(prev => ({
          ...prev,
          loading: false,
          result: hasVisibleResult ? payload : null,
          error: hasVisibleResult ? '' : 'No recommendation data returned for this selection.',
        }));
      })
      .catch(err => setRecPanel(prev => ({
        ...prev,
        loading: false,
        error: err.response?.data?.detail || err.message || 'Request failed',
      })));
  }, [hideAllTooltips]);

  // Listen for "View in Graph" highlight requests from RecommendationsTab
  React.useEffect(() => {
    const handler = (e) => {
      const names = e.detail?.names;  // array of node names to highlight
      if (Array.isArray(names) && names.length > 0) {
        const nameSet = new Set(names.map(n => (n || '').toLowerCase()));
        setHighlightedNodeNames(nameSet);
        // Auto-clear highlight after 15 seconds
        const timeoutId = setTimeout(() => setHighlightedNodeNames(new Set()), HIGHLIGHT_AUTO_CLEAR_MS);
        timeoutsRef.current.add(timeoutId);
      }
    };
    window.addEventListener('dt-highlight-nodes', handler);

    // Pick up any highlight that was queued before this component mounted
    // (e.g. fired from RecommendationsTab before the graph tab was active)
    if (window.__dt_pending_highlight) {
      handler({ detail: { names: window.__dt_pending_highlight } });
      delete window.__dt_pending_highlight;
    }

    return () => {
      window.removeEventListener('dt-highlight-nodes', handler);
      // Clear all pending timeouts
      // eslint-disable-next-line react-hooks/exhaustive-deps
      const timeouts = timeoutsRef.current;
      timeouts.forEach(id => clearTimeout(id));
      timeouts.clear();
    };
  }, []);

  // Listen for "View in Graph" load requests from RecommendationsTab.
  // Fetches all named result nodes from the backend and replaces the current graph.
  React.useEffect(() => {
    const loadResultNodes = async (names) => {
      if (!names || names.length === 0) return;
      setSearchLoading(true);
      try {
        const response = await apiClient.post(API.graph.graphfilterMulti, { names });
        const results = response.data?.results || [];

        const nodesMap = new Map();
        const rawLinks = new Map();

        results.forEach(record => {
          const n = record['n'];
          const r = record['r'];
          const m = record['m'];

          if (n) {
            const id = n.elementId;
            if (!nodesMap.has(id)) {
              nodesMap.set(id, { ...n.properties, elementId: id, labels: n.labels || ['Node'], label: n.labels?.[0] || 'Node' });
            }
          }
          if (r && m) {
            const mid = m.elementId;
            if (!nodesMap.has(mid)) {
              nodesMap.set(mid, { ...m.properties, elementId: mid, labels: m.labels || ['Node'], label: m.labels?.[0] || 'Node' });
            }
            if (!rawLinks.has(r.elementId)) {
              rawLinks.set(r.elementId, { elementId: r.elementId, source: r.start, target: r.end, type: r.type, properties: r.properties });
            }
          }
        });

        const nodes = Array.from(nodesMap.values());
        const nodeIds = new Set(nodes.map(n => n.elementId));
        const links = Array.from(rawLinks.values()).filter((l) => {
          const sourceId = getLinkEndpointId(l.source);
          const targetId = getLinkEndpointId(l.target);
          return nodeIds.has(sourceId) && nodeIds.has(targetId);
        });

        const labelSet = new Set();
        nodes.forEach(n => (n.labels || []).forEach(l => labelSet.add(l)));

        startTransition(() => {
          setSearchResultData({ nodes, links });
          if (!graphSearchActiveRef.current) {
            setFilteredData({ nodes, links });
          }
          syncSharedSearchResults(nodes);
        });
      } catch (err) {
        logger.error('[dt-load-result-nodes] Error:', err.message);
      } finally {
        setSearchLoading(false);
      }
    };

    const handler = (e) => {
      const names = e.detail?.names;
      if (Array.isArray(names) && names.length > 0) loadResultNodes(names);
    };

    window.addEventListener('dt-load-result-nodes', handler);
    // Pick up any pending load queued before this component processed the event
    if (window.__dt_pending_result_nodes) {
      loadResultNodes(window.__dt_pending_result_nodes);
      delete window.__dt_pending_result_nodes;
    }
    return () => window.removeEventListener('dt-load-result-nodes', handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiClient]);

  // ── Chat Results → Graph: extract entity names from chat response and load/highlight them ──
  React.useEffect(() => {
    if (!chatResults || !Array.isArray(chatResults) || chatResults.length === 0) return;
    const latest = chatResults[chatResults.length - 1];
    if (!latest?.response) return;

    const responseText = latest.response;

    // Extract entity/node names from the chat response using multiple heuristics:
    // 1. Bold text (**Name**) often indicates entities
    // 2. Backtick text (`Name`) indicates code/identifiers
    // 3. Quoted text ("Name")
    // 4. Lines that look like list items with entity names
    const extracted = new Set();

    // Pattern 1: **bold text** (commonly entity names in LLM responses)
    const boldMatches = responseText.matchAll(/\*\*([^*]{2,60})\*\*/g);
    for (const m of boldMatches) {
      const val = m[1].trim();
      // Skip generic phrases that aren't entity names
      if (val.length > 2 && !/^(note|example|result|answer|summary|warning|important|error|tip)$/i.test(val)) {
        extracted.add(val);
      }
    }

    // Pattern 2: `backtick text` (identifiers/codes)
    const codeMatches = responseText.matchAll(/`([^`]{2,60})`/g);
    for (const m of codeMatches) {
      const val = m[1].trim();
      if (val.length > 2 && !val.includes(' ') && !/^(true|false|null|undefined|none)$/i.test(val)) {
        extracted.add(val);
      }
    }

    // Pattern 3: Named entities from structured patterns like "Name:" or "- Name"
    const listMatches = responseText.matchAll(/(?:^|\n)\s*[-•]\s*\*?\*?([A-Z][A-Za-z0-9_\-. ]{2,50})/g);
    for (const m of listMatches) {
      const val = m[1].trim().replace(/\*+$/, '');
      if (val.length > 2) extracted.add(val);
    }

    if (extracted.size === 0) return;

    const names = Array.from(extracted);

    // Load the matched nodes into the graph and highlight them
    window.dispatchEvent(new CustomEvent('dt-load-result-nodes', { detail: { names } }));
    // Also highlight them visually
    const highlightTimeoutId = setTimeout(() => {
      window.dispatchEvent(new CustomEvent('dt-highlight-nodes', { detail: { names } }));
    }, ENTITY_EXTRACTION_DELAY_MS);
    // Track timeout for cleanup
    timeoutsRef.current.add(highlightTimeoutId);
  }, [chatResults]);

  // Helper: build recommendation action bar HTML for node tooltips
  const buildRecActionBar = (node) => {
    const nodeName = resolveNodeName(node);
    if (!nodeName || nodeName === 'Unknown') return '';
    const { isPartLike, isChangeLike } = getNodeSemanticHints(node);
    const escapedName = escapeHtml(nodeName || '');
    const nodeId = escapeHtml(node?.elementId || node?.id || '');
    const props = node?.properties && typeof node.properties === 'object' ? node.properties : {};
    const ontologyPrefix = escapeHtml(props.prefix || props.ontology_prefix || '');
    const ontologyId = escapeHtml(props.ontology_id || props.source_ontology || '');
    const btnStyle = 'display:inline-block;padding:4px 10px;border:none;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;color:#fff;';
    const buttons = [];

    if (isPartLike || isChangeLike) {
      buttons.push(`<button type="button" class="dt-rec-btn" data-rec-service="change-impact" data-rec-node="${escapedName}" data-rec-node-id="${nodeId}" data-rec-prefix="${ontologyPrefix}" data-rec-ontology-id="${ontologyId}" style="${btnStyle}background:#C05621;" title="Assess downstream change impact">Impact</button>`);
    }
    if (isPartLike) {
      buttons.push(`<button type="button" class="dt-rec-btn" data-rec-service="similar-parts" data-rec-node="${escapedName}" data-rec-node-id="${nodeId}" data-rec-prefix="${ontologyPrefix}" data-rec-ontology-id="${ontologyId}" style="${btnStyle}background:#1F3D63;" title="Find comparable parts">Similar Parts</button>`);
      buttons.push(`<button type="button" class="dt-rec-btn" data-rec-service="manufacturing" data-rec-node="${escapedName}" data-rec-node-id="${nodeId}" data-rec-prefix="${ontologyPrefix}" data-rec-ontology-id="${ontologyId}" style="${btnStyle}background:#486581;" title="Review manufacturing processes">Manufacturing</button>`);
    }

    if (buttons.length === 0) return '';

    return `
      <div style="padding:6px 8px 4px;margin-bottom:4px;border-bottom:1px solid #e2e6ea;display:flex;flex-wrap:wrap;gap:6px;">
        ${buttons.join('')}
      </div>`;
  };

  // Schema-driven display
  const { getDisplayLabel: schemaDisplayLabel } = useSchema() || {};

  // Performance: Optimize state management
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [filteredData, setFilteredData] = useState({ nodes: [], links: [] });
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  // Performance: Add loading states for better UX
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResultMode, setSearchResultMode] = useState('broader');
  const [isLayoutSwitching] = useState(false);
  // New state for expand/collapse functionality
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [loadingNodes, setLoadingNodes] = useState(new Set());
  const [fullDataset, setFullDataset] = useState({ nodes: [], links: [] });
  // New state to track initial data for reset functionality
  const [initialData, setInitialData] = useState({ nodes: [], links: [] });
  // Track which nodes were added by each expansion
  const [nodeExpansions, setNodeExpansions] = useState(new Map());
  // Track expanded nodes specifically for the indented tree layout
  const [treeExpandedNodes, setTreeExpandedNodes] = useState(new Set());
  // New state for layout selection
  const [layoutType] = useState('force-directed');
  const [prevLayoutType, setPrevLayoutType] = useState('force-directed');
  // Unified primary button color (match WhereUsedView request)

  // ── Recommendation: highlighted node names (set via "View in Graph") ──
  const [highlightedNodeNames, setHighlightedNodeNames] = useState(new Set());

  // ── Recommendation: slide-in panel state ──
  const [recPanel, setRecPanel] = useState({ open: false, service: null, nodeName: '', loading: false, result: null, error: '' });
  const resetGraphSelectionState = useCallback((options = {}) => {
    const {
      resetOntology = true,
      resetStepPart = true,
      resetSearch = true,
      resetExpansion = true,
      resetInteraction = true,
      dataOverride = null,
    } = options;

    if (resetSearch) {
      setSearchQuery('');
      setSearchInput('');
      setSearchResultData({ nodes: [], links: [] });
      setContextualSearchResults([]);
      setHighlightedNodeIds(new Set());
      setActiveSearchResultId(null);
    }
    if (resetExpansion) {
      const clearedExpanded = new Set();
      const clearedExpansions = new Map();
      setExpandedNodes(clearedExpanded);
      setNodeExpansions(clearedExpansions);
      setTreeExpandedNodes(new Set());
      expandedNodesRef.current = clearedExpanded;
      nodeExpansionsRef.current = clearedExpansions;
    }
    if (resetOntology) {
      setSelectedOntology('ALL');
      selectedOntologyRef.current = 'ALL';
      setStepParts([]);
    }
    if (resetStepPart) {
      setSelectedStepPart('ALL');
    }
    if (resetInteraction) {
      userInteractedWithGraphRef.current = false;
      lastCenteredSearchRef.current = '';
    }
    if (dataOverride) {
      setData(dataOverride);
    }
  }, [setData]);

  useEffect(() => {
    const handleSchemaCleaned = () => {
      const empty = { nodes: [], links: [] };
      setGraphData(empty);
      setFilteredData(empty);
      setFullDataset(empty);
      setInitialData(empty);
      setLoadingNodes(new Set());
      setError(null);
      resetGraphSelectionState({ dataOverride: empty });
    };
    window.addEventListener('dt-schema-cleaned', handleSchemaCleaned);
    return () => window.removeEventListener('dt-schema-cleaned', handleSchemaCleaned);
  }, [resetGraphSelectionState, setData]);
  // Search result state: stores raw search results and active selection
  const [searchResultData, setSearchResultData] = useState({ nodes: [], links: [] });
  const [, setContextualSearchResults] = useState([]);
  const [highlightedNodeIds, setHighlightedNodeIds] = useState(new Set());
  const [activeSearchResultId, setActiveSearchResultId] = useState(null);
  const [contextualRootNodeId, setContextualRootNodeId] = useState(null);
  const filteredDataRef = useRef(filteredData);
  const searchResultDataRef = useRef(searchResultData);
  const highlightedNodeIdsRef = useRef(highlightedNodeIds);
  const activeSearchResultIdRef = useRef(null);
  const contextualRootNodeIdRef = useRef(null);
  const searchModeRef = useRef(false);
  const expandedNodesRef = useRef(new Set());
  const nodeExpansionsRef = useRef(new Map());
  const contextualSearchRequestIdRef = useRef(0);
  // ── Graph View Mode: 'ontology' = Ontology Graph Visualization, 'individual' = Contextual Individual Graph View
  const [graphViewMode, setGraphViewMode] = useState('ontology');
  const graphViewModeRef = useRef('ontology');
  // Ontology viewer state
  const [selectedOntology, setSelectedOntology] = useState('ALL');
  const selectedOntologyRef = useRef('ALL');
  const lastSpecificOntologyRef = useRef('ALL');
  const lastNeo4jConnectedRef = useRef(null);
  // Local loading state for ontology-specific operations (separate from context loading)
  const [, setOntologyLoading] = useState(false);
  const [ontologyGraphMessage, setOntologyGraphMessage] = useState('');
  // Ontology options loaded from centralized context (shared across all components)
  const {
    ontologies: ontologyOptions,
    loading: ontologyLoading,
    error: ontologyError,
  } = useOntologies();
  const [stepParts, setStepParts] = useState([]); // available STEP part names
  const [selectedStepPart, setSelectedStepPart] = useState('ALL');
  const [stepPartsLoading, setStepPartsLoading] = useState(false);
  const [stepPartsError, setStepPartsError] = useState(null);
  // Performance: Debounced search query
  const debouncedSearchQuery = useDebounce(searchQuery, 300); // 300ms delay
  const debouncedSearchQueryRef = useRef(debouncedSearchQuery);
  const searchInputRef = useRef(searchInput);
  const submitSearchQuery = useCallback((queryOverride) => {
    const nextQuery = typeof queryOverride === 'string' ? queryOverride : searchInputRef.current;
    setSearchQuery(normalizeSearchTerm(nextQuery));
  }, []);
  // Performance: Memoized search function
  const nodeSearchFunction = useMemo(() => createNodeSearchFunction(), []);
  const graphSearchActive = useMemo(
    () => Boolean(searchQuery || debouncedSearchQuery),
    [searchQuery, debouncedSearchQuery]
  );
  const graphSearchActiveRef = useRef(graphSearchActive);
  const isOntologyGraphMode = graphViewMode === 'ontology' && selectedOntology !== 'ALL';
  const isFullGraphMode = graphViewMode === 'ontology' && selectedOntology === 'ALL';
  const activeDisplayData = useMemo(() => {
    if (graphViewMode === 'individual') {
      return filteredData;
    }

    if (graphSearchActive) {
      return searchResultData?.nodes?.length > 0
        ? searchResultData
        : { nodes: [], links: [] };
    }

    return graphData?.nodes?.length || graphData?.links?.length
      ? graphData
      : filteredData;
  }, [filteredData, graphData, graphSearchActive, graphViewMode, searchResultData]);
  const activeGraphDataset = useMemo(() => {
    if (graphViewMode === 'individual') {
      return filteredData?.nodes?.length > 0 ? filteredData : { nodes: [], links: [] };
    }
    if (activeDisplayData?.nodes?.length > 0) {
      return activeDisplayData;
    }
    if (graphSearchActive) {
      return { nodes: [], links: [] };
    }
    return graphData;
  }, [activeDisplayData, filteredData, graphData, graphSearchActive, graphViewMode]);
  const ontologySliceSummary = useMemo(() => {
    if (graphViewMode !== 'ontology' || selectedOntology === 'ALL') {
      return null;
    }

    const nodes = Array.isArray(activeGraphDataset?.nodes) ? activeGraphDataset.nodes : [];
    const links = Array.isArray(activeGraphDataset?.links) ? activeGraphDataset.links : [];
    if (nodes.length === 0 && links.length === 0) {
      return null;
    }

    const relationshipOrder = [
      'SUBCLASS_OF',
      'DOMAIN',
      'RANGE',
      'SUBPROPERTY_OF',
      'EQUIVALENT_CLASS',
      'DISJOINT_WITH',
      'MASTER_REFERENCE',
      'RELATED_REFERENCE',
      'PART_REFERENCE',
      'INSTANCE_REFERENCE',
      'PARENT_REFERENCE',
      'SATISFIES',
      'GENERAL_RELATION',
      'TRACE_LINK',
    ];
    const relationshipCounts = links.reduce((acc, link) => {
      const type = safeString(link?.type, 'RELATED_TO');
      acc[type] = (acc[type] || 0) + 1;
      return acc;
    }, {});

    const schemaLabelCounts = nodes.reduce((acc, node) => {
      const labels = Array.isArray(node?.labels) ? node.labels : [];
      const schemaLabel = labels.find((label) => ['OntologyClass', 'ObjectProperty', 'DatatypeProperty'].includes(label));
      if (schemaLabel) {
        acc[schemaLabel] = (acc[schemaLabel] || 0) + 1;
      }
      return acc;
    }, {});

    const visibleRelationships = relationshipOrder
      .filter((type) => relationshipCounts[type] > 0)
      .map((type) => ({ type, count: relationshipCounts[type] }));

    const visibleSchemaLabels = [
      { label: 'Classes', key: 'OntologyClass' },
      { label: 'Object properties', key: 'ObjectProperty' },
      { label: 'Datatype properties', key: 'DatatypeProperty' },
    ].filter((entry) => schemaLabelCounts[entry.key] > 0)
      .map((entry) => ({ label: entry.label, count: schemaLabelCounts[entry.key] }));

    return {
      nodeCount: nodes.length,
      relationshipCount: links.length,
      visibleRelationships,
      visibleSchemaLabels,
      hasSubclassEdges: Boolean(relationshipCounts.SUBCLASS_OF),
    };
  }, [activeGraphDataset, graphViewMode, selectedOntology]);

  const findBestSearchMatchId = useCallback((nodes, query) => {
    const term = normalizeSearchTerm(query);
    if (!term || !Array.isArray(nodes) || nodes.length === 0) return null;

    const pickField = (node, fields) => {
      for (const field of fields) {
        const value = node?.properties?.[field] ?? node?.[field];
        const text = String(value ?? '').trim().toLowerCase();
        if (!text) continue;
        if (text === term) return 1000;
        if (text.startsWith(term)) return 800;
        if (text.includes(term)) return 500;
      }
      return 0;
    };

      const candidates = nodes.map((node) => ({
      id: node.elementId,
      score: Math.max(
        pickField(node, ['elementId']),
        pickField(node, ['id', 'uid', 'instance_id', 'identifier', 'catalogue_id', 'requirement_id', 'requirement_ref']),
        pickField(node, ['name', 'title', 'label', 'display_name', 'displayName', 'code']),
        pickField(node, ['source_filename', 'filename', 'file_name', 'file']),
        pickField(node, ['external_id', 'externalId', 'href', 'idref'])
      ),
    })).filter((entry) => entry.score > 0);

    candidates.sort((a, b) => b.score - a.score);
    return candidates[0]?.id || nodes[0]?.elementId || null;
  }, []);

  const findPreferredContextualRootId = useCallback((nodes, query) => {
    const term = normalizeSearchTerm(query);
    if (!Array.isArray(nodes) || nodes.length === 0) return null;

    const getValue = (node, keys) => {
      for (const key of keys) {
        const value = node?.properties?.[key] ?? node?.[key];
        const text = String(value ?? '').trim();
        if (text) return text;
      }
      return '';
    };

    const scored = nodes.map((node) => {
      const baseScore = Number(findBestSearchMatchId([node], query) ? 1 : 0);
      const catalogueId = getValue(node, ['catalogue_id', 'requirement_id', 'requirement_ref']).toLowerCase();
      const isRequirementRevision = hasNodeLabel(node, 'RequirementRevision');
      const isRequirement = hasNodeLabel(node, 'Requirement');
      const isGeneralRelation = hasNodeLabel(node, 'GeneralRelation');

      let contextualBonus = 0;
      if (term.startsWith('req')) {
        if (catalogueId.startsWith(term)) contextualBonus += 2000;
        if (isRequirementRevision) contextualBonus += 400;
        else if (isRequirement) contextualBonus += 250;
      }

      if (isGeneralRelation) contextualBonus -= 300;

      return {
        id: node?.elementId,
        score: contextualBonus + baseScore,
      };
    }).filter((entry) => entry.id);

    scored.sort((a, b) => b.score - a.score);
    return scored[0]?.id || findBestSearchMatchId(nodes, query) || nodes[0]?.elementId || null;
  }, [findBestSearchMatchId]);

  const syncSharedSearchResults = useCallback((nodes, { clear = false, force = false } = {}) => {
    if (!setSearchResults) return;
    if (graphViewModeRef.current === 'individual') {
      if (clear) setSearchResults([]);
      return;
    }
    if (!clear && graphSearchActive && !force) {
      return;
    }
    setSearchResults(nodes);
  }, [setSearchResults, graphSearchActive]);

  const clearExpansionState = useCallback(() => {
    const clearedExpanded = new Set();
    const clearedExpansions = new Map();
    setExpandedNodes(clearedExpanded);
    setNodeExpansions(clearedExpansions);
    setTreeExpandedNodes(new Set());
    setLoadingNodes(new Set());
    expandedNodesRef.current = clearedExpanded;
    nodeExpansionsRef.current = clearedExpansions;
  }, []);

  const syncContextualHighlights = useCallback((query, nodesOverride = null) => {
    const sourceNodes = Array.isArray(nodesOverride)
      ? nodesOverride
      : (filteredDataRef.current?.nodes || []);
    const matches = query ? nodeSearchFunction(sourceNodes, query) : [];
    setHighlightedNodeIds(new Set(matches.map((node) => node.elementId)));
  }, [nodeSearchFunction]);

  const resolveSearchBaseDataset = useCallback(() => {
    if (graphViewModeRef.current === 'individual') {
      return filteredDataRef.current?.nodes?.length ? filteredDataRef.current : { nodes: [], links: [] };
    }

    if (selectedOntologyRef.current && selectedOntologyRef.current !== 'ALL') {
      return filteredDataRef.current?.nodes?.length
        ? filteredDataRef.current
        : (graphData.nodes?.length ? graphData : { nodes: [], links: [] });
    }

    if (initialData?.nodes?.length) return initialData;
    if (graphData.nodes?.length) return graphData;
    return { nodes: [], links: [] };
  }, [graphData, initialData]);

  const buildSearchResultSlice = useCallback((baseData, query, mode = 'broader') => {
    const safeBase = baseData?.nodes?.length || baseData?.links?.length
      ? baseData
      : { nodes: [], links: [] };
    const matchedNodes = nodeSearchFunction(
      (safeBase.nodes || []).filter((node) => !isMetadataWrapperNode(node)),
      query
    );
    const selectedNodes = mode === 'best'
      ? matchedNodes.slice(0, 1)
      : matchedNodes.slice(0, 80);
    const selectedNodeIds = new Set(selectedNodes.map((node) => node.elementId));
    const selectedLinks = (safeBase.links || []).filter((link) => {
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      return selectedNodeIds.has(sourceId) || selectedNodeIds.has(targetId);
    });
    const contextualNodeIds = new Set(selectedNodeIds);
    selectedLinks.forEach((link) => {
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      if (sourceId) contextualNodeIds.add(sourceId);
      if (targetId) contextualNodeIds.add(targetId);
    });
    const contextualNodes = (safeBase.nodes || []).filter((node) => contextualNodeIds.has(node.elementId));

    return {
      nodes: contextualNodes,
      links: selectedLinks,
    };
  }, [nodeSearchFunction]);

  const commitGraphSlice = useCallback((nextData, options = {}) => {
    const {
      updateFilteredData = true,
      updateGraphData = false,
      updateFullDataset = false,
      updateSearchResultData = false,
      nextActiveSearchId,
      clearActiveSearchId = false,
      resetCenteredSearch = false,
      syncResults = false,
      forceSearchResults = false,
    } = options;

    const normalizedSlice = deduplicateNodesAndLinks(nextData?.nodes || [], nextData?.links || []);
    const validatedSlice = validateConnectivity(normalizedSlice);
    const connectedNodeIds = new Set();
    (normalizedSlice.links || []).forEach((link) => {
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      if (sourceId) connectedNodeIds.add(sourceId);
      if (targetId) connectedNodeIds.add(targetId);
    });
    const prunedSlice = (normalizedSlice.links || []).length > 0
      ? {
          nodes: (normalizedSlice.nodes || []).filter((node) => connectedNodeIds.has(node.elementId)),
          links: (normalizedSlice.links || []).filter((link) => {
            const sourceId = getLinkEndpointId(link.source);
            const targetId = getLinkEndpointId(link.target);
            return connectedNodeIds.has(sourceId) && connectedNodeIds.has(targetId);
          }),
        }
      : normalizedSlice;
    if (validatedSlice.orphanNodeIds.length > 0 && isDevelopment) {
      performanceWarn('[GRAPH] commitGraphSlice orphan nodes detected:', validatedSlice.orphanNodeIds);
    }

    if (updateFilteredData) setFilteredData(prunedSlice);
    setData(prunedSlice);
    if (updateGraphData) setGraphData(prunedSlice);
    if (updateFullDataset) setFullDataset(prunedSlice);
    if (updateSearchResultData) setSearchResultData(prunedSlice);

    if (clearActiveSearchId) {
      setActiveSearchResultId(null);
      activeSearchResultIdRef.current = null;
    } else if (typeof nextActiveSearchId !== 'undefined') {
      setActiveSearchResultId(nextActiveSearchId);
      activeSearchResultIdRef.current = nextActiveSearchId;
    }

    if (resetCenteredSearch) {
      lastCenteredSearchRef.current = '';
    }

    if (syncResults) {
      syncSharedSearchResults(prunedSlice.nodes || [], { force: forceSearchResults });
    }
  }, [setData, syncSharedSearchResults]);

  const loadContextualRootGraph = useCallback(async (nodeId, { preserveSearch = true } = {}) => {
    if (!nodeId) return;

    setSearchLoading(true);
    try {
      const candidateNodes = [
        ...(searchResultDataRef.current?.nodes || []),
        ...(filteredDataRef.current?.nodes || []),
      ];
      const selectedNode = candidateNodes.find((node) => node?.elementId === nodeId) || null;
      const semanticRequirementRoot = isRequirementContextNode(selectedNode);
      const traversalDepth = 1;
      const response = await graphApi.getTraversal(nodeId, traversalDepth);
      const traversalData = normalizeGraphDataset(response.data, { collapseHiddenBridges: semanticRequirementRoot });
      const rootedData = semanticRequirementRoot
        ? traversalData
        : getOneHopNeighborhood(traversalData, nodeId);

      clearExpansionState();
      setContextualRootNodeId(nodeId);
      setContextualSearchResults([]);
      commitGraphSlice(rootedData, {
        updateFilteredData: true,
        updateGraphData: false,
        updateFullDataset: false,
        updateSearchResultData: true,
        nextActiveSearchId: nodeId,
        resetCenteredSearch: true,
        syncResults: preserveSearch,
        forceSearchResults: preserveSearch,
      });

      if (preserveSearch) {
        syncContextualHighlights(debouncedSearchQueryRef.current, rootedData.nodes);
        syncSharedSearchResults(rootedData.nodes || [], { force: true });
      } else {
        setSearchQuery('');
        setSearchInput('');
        setHighlightedNodeIds(new Set());
      }
    } catch (loadError) {
      logger.error('[CONTEXTUAL SEARCH] Failed to load selected root graph:', loadError);
    } finally {
      setSearchLoading(false);
    }
  }, [clearExpansionState, commitGraphSlice, syncContextualHighlights, syncSharedSearchResults]);

  const selectRichContextualRootId = useCallback(async (matches, query, requestId) => {
    const dedupedMatches = (matches || []).filter((node, index, array) => (
      node?.elementId && array.findIndex((entry) => entry.elementId === node.elementId) === index
    ));

    if (dedupedMatches.length <= 1) {
      return dedupedMatches[0]?.elementId || null;
    }

    const probeCandidates = dedupedMatches.slice(0, 24);
    const scoredCandidates = await Promise.all(probeCandidates.map(async (candidate) => {
      if (requestId !== contextualSearchRequestIdRef.current) return null;

      try {
        const response = await graphApi.getTraversal(candidate.elementId, 2);
        const traversalData = normalizeGraphDataset(response.data, { collapseHiddenBridges: true });
        const nodes = traversalData.nodes || [];
        const links = traversalData.links || [];
        const nodeLabelCount = new Set((nodes || []).flatMap((node) => Array.isArray(node?.labels) ? node.labels : [])).size;
        const relTypeCount = new Set((links || []).map((link) => String(link.type || '').trim()).filter(Boolean)).size;
        const businessNodeCount = (nodes || []).filter((node) => !isMetadataWrapperNode(node)).length;
        const richTraceCount = (links || []).filter((link) => String(link?.properties?.collapsed || '') !== 'true').length;
        const score =
          (businessNodeCount * 100) +
          (links.length * 35) +
          (nodeLabelCount * 15) +
          (relTypeCount * 20) +
          (richTraceCount * 10);

        return { id: candidate.elementId, score };
      } catch (error) {
        logger.warn('[CONTEXTUAL SEARCH] Root richness probe failed for candidate:', candidate?.elementId, error?.message || error);
        return { id: candidate.elementId, score: -1 };
      }
    }));

    const ranked = scoredCandidates.filter(Boolean).sort((a, b) => b.score - a.score);
    const bestRichRoot = ranked[0]?.id;
    return bestRichRoot || findPreferredContextualRootId(dedupedMatches, query);
  }, [findPreferredContextualRootId]);

  const loadContextualSearchMatch = useCallback(async (matches, query, requestId, sourceGraph = null) => {
    const dedupedMatches = matches.filter((node, index, array) => (
      array.findIndex((entry) => entry.elementId === node.elementId) === index
    ));
    const bestMatchId = (
      await selectRichContextualRootId(dedupedMatches, query, requestId)
    ) || findPreferredContextualRootId(dedupedMatches, query) || dedupedMatches[0]?.elementId || null;

    if (!bestMatchId) {
      setContextualSearchResults([]);
      setHighlightedNodeIds(new Set());
      setSearchLoading(false);
      return;
    }

    if (requestId !== contextualSearchRequestIdRef.current) {
      return;
    }

    setContextualSearchResults([]);
    if (searchResultMode !== 'best') {
      clearExpansionState();
      setContextualRootNodeId(bestMatchId);
      const connectedSlice = buildSearchResultSlice(
        sourceGraph || { nodes: dedupedMatches, links: [] },
        query,
        'broader'
      );
      commitGraphSlice(connectedSlice, {
        updateFilteredData: true,
        updateSearchResultData: true,
        nextActiveSearchId: bestMatchId,
        resetCenteredSearch: true,
        syncResults: true,
        forceSearchResults: true,
      });
      syncContextualHighlights(query, connectedSlice.nodes);
      syncSharedSearchResults(connectedSlice.nodes || [], { force: true });
      setSearchLoading(false);
      return;
    }
    await loadContextualRootGraph(bestMatchId, { preserveSearch: true });
  }, [buildSearchResultSlice, clearExpansionState, commitGraphSlice, findPreferredContextualRootId, loadContextualRootGraph, searchResultMode, selectRichContextualRootId, syncContextualHighlights, syncSharedSearchResults]);

  const resolveContextualEntryNodeId = useCallback((queryOverride = '') => {
    const queryTerm = normalizeSearchTerm(queryOverride || debouncedSearchQueryRef.current || searchInput || searchQuery);
    const candidateMap = new Map();

    [...(searchResultDataRef.current?.nodes || []), ...(filteredDataRef.current?.nodes || [])]
      .filter((node) => (
        node?.elementId
        && !isMetadataWrapperNode(node)
        && !isSchemaTerminalNode(node)
      ))
      .forEach((node) => {
        if (!candidateMap.has(node.elementId)) {
          candidateMap.set(node.elementId, node);
        }
      });

    const candidates = Array.from(candidateMap.values());
    if (candidates.length === 0) return null;
    return findBestSearchMatchId(candidates, queryTerm) || candidates[0]?.elementId || null;
  }, [findBestSearchMatchId, searchInput, searchQuery]);

  const preferredOntologyValue = useMemo(() => {
    if (selectedOntology && selectedOntology !== 'ALL') return selectedOntology;
    const candidates = (ontologyOptions || []).filter((option) => option?.value && option.value !== 'ALL' && !option.disabled);
    const preferred = candidates.find((option) => Number(option.relationship_count || 0) > 0) || candidates[0];
    return preferred?.value || 'ALL';
  }, [ontologyOptions, selectedOntology]);

  useEffect(() => {
    activeSearchResultIdRef.current = activeSearchResultId;
  }, [activeSearchResultId]);
  useEffect(() => {
    contextualRootNodeIdRef.current = contextualRootNodeId;
  }, [contextualRootNodeId]);
  useEffect(() => {
    filteredDataRef.current = filteredData;
  }, [filteredData]);
  useEffect(() => {
    searchResultDataRef.current = searchResultData;
  }, [searchResultData]);
  useEffect(() => {
    highlightedNodeIdsRef.current = highlightedNodeIds;
  }, [highlightedNodeIds]);
  useEffect(() => {
    expandedNodesRef.current = expandedNodes;
  }, [expandedNodes]);
  useEffect(() => {
    nodeExpansionsRef.current = nodeExpansions;
  }, [nodeExpansions]);
  useEffect(() => {
    searchInputRef.current = searchInput;
  }, [searchInput]);
  useEffect(() => {
    debouncedSearchQueryRef.current = debouncedSearchQuery;
  }, [debouncedSearchQuery]);
  useEffect(() => {
    graphSearchActiveRef.current = graphSearchActive;
  }, [graphSearchActive]);
  const getCurrentGraphSlice = useCallback(() => {
    if (graphViewModeRef.current === 'individual') {
      return filteredDataRef.current;
    }
    return graphSearchActiveRef.current && (searchResultDataRef.current.nodes?.length || 0) > 0
      ? searchResultDataRef.current
      : filteredDataRef.current;
  }, []);

  // Performance: Memoized color mapping - GENERIC VERSION
  const getNodeColor = useCallback((nodeLike) => {
    const label = resolveNodeType(nodeLike);
    if (!label) return TCS_GRAPH_THEME.inkMuted;
    const subtypeKey = resolveNodeColorKey(nodeLike);

    // Explicit color map for known ontology labels - optimized for clarity
    const colorMap = {
      // Ontology Schema Layer (Classes and Properties)
      'OntologyClass':     '#1F3D63',
      'Class':             '#274C77',
      'ObjectProperty':    '#5D6D7E',
      'DatatypeProperty':  '#8D6E63',
      'OntologyProperty':  '#5D6D7E',
      'Property':          '#5D6D7E',
      'Relationship':      '#486581',
      'Annotation':        '#7B8794',

      // Instance Data Layer
      'Individual':        '#486581',
      'Resource':          '#61788A',
      'Datum':             '#61788A',

      // CAD/PLM Specific
      'Part':              '#355C7D',
      'SurfaceFinish':     '#8D6E63',
      'Dimension':         '#486581',
      'GeometricTolerance':'#3E4C59',

      // File Types
      'PLMXMLFile':        '#7B8794',
      'StepFile':          '#9AA5B1',
      'StepInstance':      '#52606D',
    };

    if (colorMap[subtypeKey]) return colorMap[subtypeKey];
    if (colorMap[label]) return colorMap[label];

    const normalizedLabel = String(subtypeKey || label).toLowerCase();
    if (normalizedLabel.includes('property')) return '#6B7280';
    if (normalizedLabel.includes('class')) return '#1F3D63';
    if (normalizedLabel.includes('assembly') || normalizedLabel.includes('bom')) return '#0E7490';
    if (normalizedLabel.includes('product')) return '#274C77';
    if (normalizedLabel.includes('part')) return '#355C7D';
    if (normalizedLabel.includes('requirement')) return '#7C3AED';
    if (normalizedLabel.includes('document')) return '#0F766E';
    if (normalizedLabel.includes('process')) return '#C05621';
    if (normalizedLabel.includes('geometry') || normalizedLabel.includes('shape') || normalizedLabel.includes('cad')) return '#8D6E63';
    if (normalizedLabel.includes('material')) return '#A16207';
    if (normalizedLabel.includes('organization') || normalizedLabel.includes('person')) return '#BE185D';
    if (normalizedLabel.includes('instance')) return '#486581';

    return ENTITY_COLOR_SWATCH[hashText(subtypeKey) % ENTITY_COLOR_SWATCH.length];
  }, []);

  // Function to create hierarchical data from graph data for tree layout
  const createHierarchicalData = useCallback((nodes, links) => {
    // Safety checks
    if (!nodes || !Array.isArray(nodes) || nodes.length === 0) {
      return [];
    }

    if (!links || !Array.isArray(links)) {
      links = [];
    }

    performanceLog(`Creating hierarchical data from ${nodes.length} nodes and ${links.length} links`);

    // If no links, just return all nodes as flat list with level 0
    if (links.length === 0) {
      return nodes.map(node => ({
        ...node,
        properties: node.properties || {},
        labels: node.labels || ['Unknown'],
        elementId: node.elementId || 'unknown',
        level: 0,
        children: []
      }));
    }

    // Helper to obtain a stable id for any node shape
    const getNodeId = (n) => (n && (n.elementId || n.id || n.identity || n.properties?.elementId || n.properties?.id || n.properties?.identity)) || undefined;
    // Normalize elementId on all nodes to guarantee presence; ensure uniqueness
    let unknownCounter = 0;
    const usedIds = new Set();
    nodes = nodes.map((n, idx) => {
      let eid = getNodeId(n);
      if (!eid) {
        eid = `__synthetic_${unknownCounter++}`;
      }
      // Prevent collisions (e.g., multiple nodes lacking IDs all becoming 'unknown')
      if (usedIds.has(eid)) {
        let c = 1;
        const base = eid;
        while (usedIds.has(`${base}__${c}`)) c++;
        eid = `${base}__${c}`;
      }
      usedIds.add(eid);
      return { ...n, elementId: eid };
    });

    // Find root nodes (nodes with no incoming links or minimal incoming connections)
    // Generic approach: don't hardcode node types
    const incomingConnections = new Map();
    const outgoingConnections = new Map();

    // Performance: Build node index Map for O(1) lookups instead of O(n) .find() calls
    const nodeIndex = new Map(nodes.map(n => [getNodeId(n), n]));

    // Count incoming connections for each node
    links.forEach(link => {
      const rawSource = getLinkEndpointId(link.source);
      const rawTarget = getLinkEndpointId(link.target);
      const sourceId = getNodeId({ elementId: rawSource });
      const targetId = getNodeId({ elementId: rawTarget });

      // Find the actual nodes to check their types and relationship types
      const sourceNode = nodeIndex.get(sourceId);
      const targetNode = nodeIndex.get(targetId);
      const relationshipType = link.type || link.properties?.type;

      // Enhanced relationship logic based on types and relationship direction
      if (sourceNode && targetNode) {
        // Generic hierarchy rules based on relationship types
        let parentId, childId;

        // Rule 1: Check relationship type for explicit parent-child
        if (relationshipType === 'HAS_CHILD' || relationshipType === 'CONTAINS' || relationshipType === 'PARENT_OF') {
          parentId = sourceId;
          childId = targetId;
        } else if (relationshipType === 'HAS_PARENT' || relationshipType === 'BELONGS_TO' || relationshipType === 'CHILD_OF') {
          parentId = targetId;
          childId = sourceId;
        }
        // Rule 2: Default to source->target direction
        else {
          parentId = sourceId;
          childId = targetId;
        }

        if (parentId && childId) {
          incomingConnections.set(childId, (incomingConnections.get(childId) || 0) + 1);
          outgoingConnections.set(parentId, (outgoingConnections.get(parentId) || 0) + 1);
          logger.sync(`[Hierarchy] Set parent: ${parentId?.substring(0,8)} -> child: ${childId?.substring(0,8)}`);
        }
      } else {
        // Fallback to normal relationship if nodes not found
        incomingConnections.set(targetId, (incomingConnections.get(targetId) || 0) + 1);
        outgoingConnections.set(sourceId, (outgoingConnections.get(sourceId) || 0) + 1);
      }
    });

    // Debug: Show connection counts for a few nodes
    const debugNodes = Array.from(incomingConnections.entries()).slice(0, 5);
    performanceLog('Sample incoming connections:', debugNodes);

    // Find potential root nodes - handle expanded datasets better.
    // Contextual instance view should stay anchored to the graph topology
    // instead of re-rooting around search hits or expansion state.
    let roots;
    const isContextualInstanceView = graphViewModeRef.current === 'individual';

    if (!isContextualInstanceView && expandedNodesRef.current.size > 0) {
      // When we have expanded nodes, first try to find the originally expanded nodes as roots
      const expandedNodeIds = Array.from(expandedNodesRef.current);
      roots = nodes.filter(node => expandedNodeIds.includes(node.elementId));

      // If that gives us too many roots, prioritize by connection count
      if (roots.length > 3) {
        // Prefer nodes with more outgoing connections (likely parents)
        roots.sort((a, b) =>
          (outgoingConnections.get(b.elementId) || 0) - (outgoingConnections.get(a.elementId) || 0)
        );
        roots = roots.slice(0, 2); // Take top 2
      }

      // If no expanded nodes found as roots, fall back to nodes with no incoming connections
      if (roots.length === 0) {
        roots = nodes.filter(node => !incomingConnections.has(node.elementId));
      }

      logger.data(`Expanded dataset: Using ${roots.length} roots from ${expandedNodeIds.length} expanded nodes`);
    } else {
      // Original logic for non-expanded datasets: find nodes with no incoming connections
      roots = nodes.filter(node => !incomingConnections.has(node.elementId));
    }

    logger.data(`Nodes with no incoming connections: ${roots.length}`);

    // If no clear roots, pick all nodes with lowest incoming connections
    if (roots.length === 0) {
      const minConnections = Math.min(...Array.from(incomingConnections.values()));
      roots = nodes.filter(node =>
        (incomingConnections.get(node.elementId) || 0) === minConnections
      );
      logger.render(`No clear roots found, using ${roots.length} nodes with minimum connections (${minConnections})`);
    }

    // Still no roots? Just use all nodes as roots
    if (roots.length === 0) {
      roots = [...nodes];
      logger.data(`No roots found at all, treating all ${nodes.length} nodes as roots`);
    }

    logger.data(`Found ${roots.length} root nodes`);

    // Build hierarchy from roots
    const processedNodes = new Set();
    const hierarchy = [];

    const buildNodeHierarchy = (node, level = 0, visited = new Set()) => {
      if (!node || !node.elementId) {
        logger.warn('[Hierarchy] Invalid node passed to buildNodeHierarchy:', node);
        return null;
      }

      if (visited.has(node.elementId)) {
        logger.warn(`[Hierarchy] Circular reference detected for node ${node.elementId?.substring(0,8)} at level ${level}, breaking cycle`);
        return null;
      }

      if (level > 10) {
        logger.warn(`[Hierarchy] Maximum depth exceeded for node ${node.elementId?.substring(0,8)}`);
        return null;
      }

      visited.add(node.elementId);
      processedNodes.add(node.elementId);

      // Find children of this node using explicit relationship rules
      let children = links
        .filter(link => {
          const rawSource = getLinkEndpointId(link.source);
          const rawTarget = getLinkEndpointId(link.target);
          const sourceId = getNodeId({ elementId: rawSource });
          const targetId = getNodeId({ elementId: rawTarget });
          const relationshipType = link.type || link.properties?.type;

          const sourceNode = nodeIndex.get(sourceId);
          const targetNode = nodeIndex.get(targetId);

          if (!sourceNode || !targetNode) return false;

          // Apply generic relationship type based rules
          let isParentChild = false;

          // Rule 1: Explicit parent-child relationships
          if (relationshipType === 'HAS_CHILD' || relationshipType === 'CONTAINS' || relationshipType === 'PARENT_OF') {
            isParentChild = sourceId === node.elementId;
          } else if (relationshipType === 'HAS_PARENT' || relationshipType === 'BELONGS_TO' || relationshipType === 'CHILD_OF') {
            isParentChild = targetId === node.elementId;
          }
          // Rule 2: Default source->target
          else {
            isParentChild = sourceId === node.elementId;
          }

          return isParentChild;
        })
        .map(link => {
          const rawSource = getLinkEndpointId(link.source);
          const rawTarget = getLinkEndpointId(link.target);
          const sourceId = getNodeId({ elementId: rawSource });
          const targetId = getNodeId({ elementId: rawTarget });
          const relationshipType = link.type || link.properties?.type;

          // Determine which node is the child based on generic relationship rules
          let childId;

          if (relationshipType === 'HAS_CHILD' || relationshipType === 'CONTAINS' || relationshipType === 'PARENT_OF') {
            childId = sourceId === node.elementId ? targetId : sourceId;
          } else if (relationshipType === 'HAS_PARENT' || relationshipType === 'BELONGS_TO' || relationshipType === 'CHILD_OF') {
            childId = targetId === node.elementId ? sourceId : targetId;
          } else {
            childId = sourceId === node.elementId ? targetId : sourceId;
          }

          return nodeIndex.get(childId);
        })
        .filter(child => child && !visited.has(child.elementId))
        .map(child => {
          // Create a new visited set for each child to prevent cross-contamination between siblings
          // but include the current path to prevent cycles
          const childVisited = new Set(visited);
          return buildNodeHierarchy(child, level + 1, childVisited);
        })
        .filter(child => child !== null);

      return {
        ...node,
        labels: node.labels || ['Unknown'],
        elementId: node.elementId || 'unknown',
        level,
        children: children || []
      };
    };

    // Process each root and build initial hierarchy
    roots.forEach(root => {
      const tree = buildNodeHierarchy(root);
      if (tree) {
        hierarchy.push(tree);
        logger.render(`Built hierarchy for root ${root.elementId?.substring(0,8)} with ${tree.children?.length || 0} children`);
      }
    });

    // For expansions, reorganize hierarchy to ensure proper parent-child relationships without duplicates.
    // Skip this in contextual instance view so search focus does not get promoted to a new tree root.
    if (!isContextualInstanceView && expandedNodesRef.current.size > 0 && hierarchy.length > 0) {
      logger.render(`[Hierarchy] Reorganizing ${hierarchy.length} trees for ${expandedNodesRef.current.size} expanded nodes`);

      // Collect all nodes from current hierarchy to avoid duplicates
      const allNodesInHierarchy = new Map();
      const collectAllNodes = (node) => {
        allNodesInHierarchy.set(node.elementId, node);
        if (node.children && node.children.length > 0) {
          node.children.forEach(collectAllNodes);
        }
      };
      hierarchy.forEach(collectAllNodes);

      // For each expanded node, ensure its complete ancestry path is visible
      const updatedRoots = [];
      const processedRootIds = new Set();

      expandedNodesRef.current.forEach(expandedNodeId => {
        // Find which root tree contains this expanded node
        let containingRoot = null;
        for (const root of hierarchy) {
          const findInTree = (node) => {
            if (node.elementId === expandedNodeId) return true;
            if (node.children) {
              return node.children.some(findInTree);
            }
            return false;
          };
          if (findInTree(root)) {
            containingRoot = root;
            break;
          }
        }

        if (containingRoot && !processedRootIds.has(containingRoot.elementId)) {
          updatedRoots.push(containingRoot);
          processedRootIds.add(containingRoot.elementId);
          logger.render(`[Hierarchy] Root ${containingRoot.elementId?.substring(0,8)} contains expanded node ${expandedNodeId?.substring(0,8)}`);
        }
      });

      // Add any roots that weren't processed but should be included
      hierarchy.forEach(root => {
        if (!processedRootIds.has(root.elementId)) {
          updatedRoots.push(root);
          logger.render(`[Hierarchy] Including additional root ${root.elementId?.substring(0,8)}`);
        }
      });

      // Replace hierarchy with reorganized roots
      hierarchy.length = 0;
      hierarchy.push(...updatedRoots);
      logger.render(`[Hierarchy] Reorganized to ${hierarchy.length} root trees`);
    }

    // Add any orphaned nodes at the end
    const orphans = nodes.filter(node => !processedNodes.has(node.elementId));
    logger.render(`Adding ${orphans.length} orphaned nodes`);
    orphans.forEach(orphan => {
      hierarchy.push({
        ...orphan,
        // Ensure properties exist
        properties: orphan.properties || {},
        labels: orphan.labels || ['Unknown'],
        elementId: orphan.elementId || 'unknown',
        level: 0,
        children: []
      });
    });

    const nodesWithoutChildrenButOutgoing = nodes.filter(n => !hierarchy.some(h => h.elementId === n.elementId) && outgoingConnections.get(n.elementId) > 0).length;
    // Debug: detect duplicate IDs in input vs hierarchy total coverage
    const inputIdCount = new Set(nodes.map(n => n.elementId)).size;
    const hierarchyAllIds = new Set();
    const collectIds = (arr) => arr.forEach(n => { hierarchyAllIds.add(n.elementId); if (n.children) collectIds(n.children); });
    collectIds(hierarchy);
    logger.render(`Final hierarchy has ${hierarchy.length} top-level nodes; outgoing-without-children (pre-orphans): ${nodesWithoutChildrenButOutgoing}; inputUniqueIds=${inputIdCount}; hierarchyTotalUniqueIds=${hierarchyAllIds.size}`);
    return hierarchy;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);  // Remove dependencies that cause infinite loops

  // Unified display label helper (name + external/version when present)
  const getDisplayLabel = useCallback((node) => {
    if (!node) return 'Unknown Node';

    const props = node.properties || node;
    const nodeLabel = node.labels?.[0] || node.label || '';

    // Resolve property from priority list (see DISPLAY_NAME_PROPERTY at top of file)
    let primaryName = resolveDisplayProp(props);

    // Schema-driven fallback
    if (!primaryName && schemaDisplayLabel) return schemaDisplayLabel(node);

    // Heuristic fallback when configured property list yields nothing
    if (!primaryName) {
      primaryName = props.name || props.title || props.code || props.key ||
                   props.number || props.abbreviation || props.id ||
                   props.identifier || props.label || props.part_number ||
                   props.product_name || props.project_name || null;
    }

    if (primaryName) {
      const version = props.external_version || props.version;
      const versionSuffix = version ? ` (v${version})` : '';
      return formatNodeDisplay(nodeLabel, `${primaryName}${versionSuffix}`);
    }

    if (node.elementId) {
      const shortId = node.elementId.substring(0, 8);
      return nodeLabel ? `${nodeLabel} [${shortId}]` : `Node [${shortId}]`;
    }

    return nodeLabel || 'Node';
  }, [schemaDisplayLabel]);

  // Primary label logic used in BOTH force-directed graph and indented tree for perfect parity
  // const getPrimaryNodeLabel = useCallback((d) => {
  //   if (!d) return 'Unknown';

  //   // Generic approach: try common name/title properties first
  //   const props = d.properties || d;
  //   const name = props.name || props.title || props.abbreviation || props.key || props.code || d.name || d.title;

  //   // Try to add version if available (comma style for consistency)
  //   const version = props.external_version || props.version || d.external_version || d.version;
  //   if (name && version) return `${name}, ${version}`;
  //   if (name) return name;

  //   // Ultimate fallback
  //   return d.label || props.label || 'Unknown';
  //   return props.name
  // }, []);


// const getPrimaryNodeLabel = useCallback((d) => {
//   if (!d) return 'Unknown';
//   const props = d.properties || d;
//   logger.render("Properties: ",props)
//   return props.name || props.Name || props.PartName || props.CADDocumentName ? String(props.name) : 'Unknown';
// }, []);


const getPrimaryNodeLabel = useCallback((d) => {
  if (!d) return '';

  const props = d.properties || d;

  // Prefer true data-bearing fields; do not surface driver metadata or Neo4j labels.
  const displayValue =
    resolveDisplayProp(props) ??
    props.name ??
    props.title ??
    props.PartName ??
    props.CADDocumentName ??
    props.ObjectType ??
    props.code ??
    props.number ??
    props.id ??
    props.uid ??
    props.identifier ??
    props.instance_id ??
    props.instanceId ??
    props.external_id ??
    props.idref ??
    props.href ??
    props.uuid ??
    null;

  if (displayValue != null && String(displayValue).trim() !== '') {
    return String(displayValue);
  }

  const semanticFallback =
    resolveNodeName(d) ||
    props.label ||
    d.label ||
    d.labels?.[0] ||
    props.entity_type ||
    d.entity_type ||
    '';

  return String(semanticFallback).trim();
}, []);


  // Function to render indented tree layout
  const renderIndentedTree = useCallback((data, svg, width, height) => {
    // Safety checks
    if (!data || !data.nodes || !Array.isArray(data.nodes) || data.nodes.length === 0) {
      // Only clear the graph content, not the defs
      if (gRef.current) {
        gRef.current.selectAll('*').remove();
      }
      const g = gRef.current || svg.append('g');
      g.attr('transform', 'translate(20, 50)');
      g.append('text')
        .attr('x', 10)
        .attr('y', 100)
        .attr('font-size', '16px')
        .attr('fill', '#666')
        .text('No data available for tree layout');
      return;
    }

    logger.render(`Rendering indented tree with ${data.nodes.length} nodes`);

    // Disable zoom for tree layout
    svg.on('.zoom', null);

    let hierarchicalData = createHierarchicalData(data.nodes, data.links || []);

    // Improved fallback: if filtered (current) dataset has zero links (common after search)
    // build hierarchy ONLY over the currently visible nodes using matching links from fullDataset.
    if ((data.links?.length || 0) === 0 && (fullDataset?.links?.length || 0) > 0 && (data.nodes?.length || 0) > 0) {
      logger.render('[TreeLayout] Building subset hierarchy from fullDataset links filtered to current nodes.');
      const visibleIds = new Set(data.nodes.map(n => n.elementId));
      const subsetLinks = fullDataset.links.filter(l => {
        const s = (typeof l.source === 'object') ? (l.source.elementId || l.source.id || l.source.identity) : l.source;
        const t = (typeof l.target === 'object') ? (l.target.elementId || l.target.id || l.target.identity) : l.target;
        return visibleIds.has(s) && visibleIds.has(t);
      });
      hierarchicalData = createHierarchicalData(data.nodes, subsetLinks);
    }

    // After expansion, rebuild hierarchy with all available data to ensure proper levels
    if (expandedNodesRef.current.size > 0 && data.links && data.links.length > 0) {
      logger.render('[TreeLayout] Rebuilding hierarchy after expansion with relationship data');
      hierarchicalData = createHierarchicalData(data.nodes, data.links);
    }
    try {
      const nodesWithChildren = hierarchicalData.reduce((acc, r) => acc + ((r.children && r.children.length) ? 1 : 0), 0);
      const totalDescChildren = (function countAll(nodes){
        return nodes.reduce((acc,n)=> acc + (n.children? n.children.length : 0) + (n.children? countAll(n.children):0),0);
      })(hierarchicalData);
      logger.render('[TreeLayout] Roots:', hierarchicalData.length, 'RootsWithChildren:', nodesWithChildren, 'Total descendant links:', totalDescChildren);
    } catch(e) {
      logger.warn('[TreeLayout] Debug metrics failed', e);
    }

    // Auto-initialize: only set roots expanded by default for large datasets; leave empty for small so we can fully expand later
    if (treeExpandedNodes.size === 0 && hierarchicalData.length > 0 && data.nodes.length > 200) {
      const rootIds = hierarchicalData.map(r => r.elementId).filter(Boolean);
      if (rootIds.length > 0) {
        setTreeExpandedNodes(new Set(rootIds));
      }
    }

    // Clear existing graph content, but preserve defs
    if (gRef.current) {
      gRef.current.selectAll('*').remove();
    } else {
      // Create the main group if it doesn't exist
      gRef.current = svg.append('g');
    }

    // Flatten hierarchy honoring expansion state and ensuring correct levels
    const flattenHierarchy = (nodes, result = [], currentLevel = 0, seenIds = new Set()) => {
      if (!Array.isArray(nodes)) {
        logger.warn('[TreeLayout] flattenHierarchy received non-array nodes:', nodes);
        return result;
      }

      nodes.forEach(node => {
        if (!node || !node.elementId) {
          logger.warn('[TreeLayout] Skipping invalid node:', node);
          return;
        }

        // Skip if we've already seen this node to prevent duplicates and infinite loops
        if (seenIds.has(node.elementId)) {
          logger.warn(`[TreeLayout] Skipping duplicate node: ${node.elementId?.substring(0,8)}`);
          return;
        }

        seenIds.add(node.elementId);

        // Force the correct level assignment regardless of what's in the node
        const nodeWithLevel = {
          ...node,
          level: currentLevel,
          // Don't include children in the flattened result to prevent circular references
          children: undefined
        };
        result.push(nodeWithLevel);

        // Root nodes (level 0) should always show their immediate children
        // Other nodes only show children if expanded
        const shouldShowChildren = currentLevel === 0 || treeExpandedNodes.has(node.elementId);

        if (node.children && Array.isArray(node.children) && node.children.length > 0 && shouldShowChildren) {
          // Create a new seenIds set for each subtree to prevent cross-contamination
          // but maintain the parent chain to prevent circular references
          const childSeenIds = new Set(seenIds);
          flattenHierarchy(node.children, result, currentLevel + 1, childSeenIds);
        }
      });
      return result;
    };

    let flatNodes = flattenHierarchy(hierarchicalData, [], 0, new Set());

    // Debug: log hierarchy structure and levels
    logger.render('[TreeLayout] Hierarchy structure:');
    hierarchicalData.forEach((root, idx) => {
      logger.render(`Root ${idx}: ${root.elementId?.substring(0,8)} (${root.labels?.[0]}) - level ${root.level}`);
      const logChildren = (node, indent = '  ') => {
        if (node.children && node.children.length > 0) {
          node.children.forEach(child => {
            logger.render(`${indent}Child: ${child.elementId?.substring(0,8)} (${child.labels?.[0]}) - level ${child.level}`);
            logChildren(child, indent + '  ');
          });
        }
      };
      logChildren(root);
    });

    // Debug: log flattened nodes with levels to verify they're being set correctly
    logger.render('[TreeLayout] Flattened nodes with levels:', flatNodes.slice(0, 8).map(n => ({
      id: n.elementId?.substring(0, 8) + '...',
      level: n.level,
      label: n.labels?.[0] || 'unknown',
      expanded: treeExpandedNodes.has(n.elementId),
      isRoot: n.level === 0
    })));

    // Ensure all root nodes are always visible
    const rootsInFlattened = flatNodes.filter(n => n.level === 0);
    logger.render(`[TreeLayout] Root nodes in flattened: ${rootsInFlattened.length} of ${hierarchicalData.length} total roots`);

    // Parity logic: ensure every node in the filtered dataset has a visible row in the tree
    if (flatNodes.length < data.nodes.length) {
      // Build a unique set of all node ids reachable in the hierarchy (deduplicated)
      const allIdsSet = new Set();
      const buildIndex = {};
      const collectUnique = (arr) => arr.forEach(n => {
        if (!buildIndex[n.elementId]) buildIndex[n.elementId] = n; // index first occurrence
        if (!allIdsSet.has(n.elementId)) allIdsSet.add(n.elementId);
        if (n.children && n.children.length) collectUnique(n.children);
      });
      collectUnique(hierarchicalData);

      // Detect which node ids from data.nodes are missing currently (for diagnostics)
      const flatSet = new Set(flatNodes.map(n => n.elementId));
      const missing = data.nodes.filter(n => !flatSet.has(n.elementId));
      if (missing.length) {
        logger.render(`[TreeLayout][Parity] Missing ${missing.length} nodes in flattened view (sample up to 15):`, missing.slice(0,15).map(n => n.elementId));
      }

      // If the hierarchy covers every unique node (even if duplicates exist due to DAG), auto-expand all
      if (allIdsSet.size === data.nodes.length) {
        logger.render('[TreeLayout][Parity] Auto-expanding all nodes to achieve parity.');
        const next = new Set(allIdsSet);
        // Only update state if it changes to avoid render loops
        let changed = false;
        if (next.size !== treeExpandedNodes.size) {
          changed = true;
        } else {
          for (const id of next) { if (!treeExpandedNodes.has(id)) { changed = true; break; } }
        }
        if (changed) setTreeExpandedNodes(next);
        // Re-flatten with expanded state - no need to rebuild entire hierarchy
        flatNodes = flattenHierarchy(hierarchicalData, [], 0, new Set());
      } else {
        logger.render(`[TreeLayout][Parity] Hierarchy unique coverage (${allIdsSet.size}) != data.nodes (${data.nodes.length}); not auto-expanding.`);
      }
    }
    logger.render(`Flattened hierarchy has ${flatNodes.length} nodes (target ${data.nodes.length})`);

    const rowHeight = TREE_ROW_HEIGHT_PX;
    const indentWidth = TREE_INDENT_WIDTH_PX;
    const nodeSize = 12;
    const headerHeight = 60;

    // Defensive: some layouts report svg clientHeight = 0 (e.g., flex container without explicit height)
    let effectiveHeight = height && height > (headerHeight + TREE_LAYOUT_PADDING_PX) ? height : TREE_DEFAULT_HEIGHT_PX; // fallback
    if (height <= (headerHeight + TREE_LAYOUT_PADDING_PX)) {
      logger.warn('[TreeLayout][HeightFallback] SVG height was', height, 'using fallback', effectiveHeight);
    }

    // Calculate total height needed
    const totalContentHeight = flatNodes.length * rowHeight;
    let availableHeight = effectiveHeight - headerHeight - 20; // Leave margin
    if (availableHeight <= 0) {
      availableHeight = Math.min(TREE_MIN_CONTENT_HEIGHT_PX, totalContentHeight + TREE_LAYOUT_PADDING_PX); // safety
      logger.warn('[TreeLayout][HeightFallback] Computed availableHeight <= 0; adjusted to', availableHeight);
    }
    const containerHeight = Math.min(availableHeight, totalContentHeight);
    logger.render(`[TreeLayout][Dims] width=${width} rawHeight=${height} effectiveHeight=${effectiveHeight} availableHeight=${availableHeight} containerHeight=${containerHeight} totalContentHeight=${totalContentHeight}`);

    const g = gRef.current;
    g.attr('transform', 'translate(0, 0)'); // Reset transform for tree layout

    // Add background
    g.append('rect')
      .attr('width', width - TREE_LAYOUT_PADDING_PX)
      .attr('height', containerHeight)
      .attr('fill', '#fafafa')
      .attr('stroke', '#ddd')
      .attr('rx', 5);

    // Add header with corporate styling
    const headerGroup = g.append('g');

    // Header background
    headerGroup.append('rect')
      .attr('width', width - TREE_LAYOUT_PADDING_PX)
      .attr('height', 50)
      .attr('x', 0)
      .attr('y', 0)
      .attr('fill', 'linear-gradient(135deg, #6C757D 0%, #495057 100%)')
      .attr('rx', 8);

    // Header gradient (since SVG doesn't support CSS gradients the same way)
    const gradient = g.append('defs')
      .append('linearGradient')
      .attr('id', 'headerGradient')
      .attr('x1', '0%')
      .attr('y1', '0%')
      .attr('x2', '100%')
      .attr('y2', '100%');

    gradient.append('stop')
      .attr('offset', '0%')
      .attr('stop-color', '#6C757D');

    gradient.append('stop')
      .attr('offset', '100%')
      .attr('stop-color', '#495057');

    headerGroup.select('rect').attr('fill', 'url(#headerGradient)');

    // Header text
    headerGroup.append('text')
      .attr('x', 16)
      .attr('y', 30)
      .attr('font-size', '18px')
      .attr('font-weight', 'bold')
      .attr('fill', 'white')
      .text('Hierarchical Data View');

    // Item count badge
    headerGroup.append('circle')
      .attr('cx', width - 80)
      .attr('cy', 25)
      .attr('r', 18)
      .attr('fill', 'rgba(255,255,255,0.2)');

    headerGroup.append('text')
      .attr('x', width - 80)
      .attr('y', 35)
      .attr('text-anchor', 'middle')
      .attr('font-size', '12px')
      .attr('font-weight', 'bold')
      .attr('fill', 'white')
      .text(flatNodes.length);

    // Layout info
    headerGroup.append('text')
      .attr('x', width - 140)
      .attr('y', 35)
      .attr('font-size', '12px')
      .attr('fill', 'rgba(255,255,255,0.8)')
      .attr('text-anchor', 'end')
      .text('Tree Layout');

    // State for scrolling
    let scrollOffset = 0;
    const maxVisibleRows = Math.floor(availableHeight / rowHeight);
    const needsScrolling = flatNodes.length > maxVisibleRows;

    // Create scrollable content area
    const contentArea = g.append('g')
      .attr('transform', `translate(0, ${headerHeight})`);

    // DEBUG: Allow disabling clipPath if it might be hiding content (e.g., browser quirks)
  const USE_CLIP = false; // TEMP: disable clipping to rule out hidden rows
    let scrollableContent;
    if (USE_CLIP) {
      let defs = g.select('defs');
      if (defs.empty()) defs = g.append('defs');
      const clipId = 'tree-content-clip';
      // Remove existing to avoid duplicates layering issues
      g.select(`#${clipId}`).remove();
      const clipPath = defs.append('clipPath')
        .attr('id', clipId);
      clipPath.append('rect')
        .attr('x', 10)
        .attr('y', 0)
        .attr('width', width - 20)
        .attr('height', availableHeight);
      scrollableContent = contentArea.append('g')
        .attr('clip-path', `url(#${clipId})`);
    } else {
      scrollableContent = contentArea.append('g');
      logger.warn('[TreeLayout][Debug] Clip path disabled; content may overflow.');
    }

    // Scrollable row container
    const rowContainer = scrollableContent.append('g')
      .attr('class', 'row-container');

    // Function to render rows
    const renderRows = (offset = 0) => {
      rowContainer.selectAll('*').remove();

      const rows = rowContainer.selectAll('.tree-row')
        .data(flatNodes, d => d.elementId)
        .enter()
        .append('g')
        .attr('class', 'tree-row')
        .attr('transform', (d, i) => `translate(0, ${(i * rowHeight) - offset})`);
      logger.render('[TreeLayout][RenderRows] Rendering', flatNodes.length, 'rows; offset=', offset);

      rows.append('rect')
        .attr('width', width - 40)
        .attr('height', rowHeight - 2)
        .attr('x', 20)
        .attr('fill', (d, i) => {
          const nm = (d.name || d.properties?.name || '').toLowerCase();
          if (highlightedNodeNames.has(nm)) return '#FFF9C4'; // gold highlight
          return i % 2 === 0 ? '#fdfdfd' : '#f8f9fa';
        })
        .attr('stroke', (d) => {
          const nm = (d.name || d.properties?.name || '').toLowerCase();
          return highlightedNodeNames.has(nm) ? '#FFD700' : '#c3d4e6';
        })
        .attr('stroke-width', (d) => {
          const nm = (d.name || d.properties?.name || '').toLowerCase();
          return highlightedNodeNames.has(nm) ? 2 : 1;
        })
        .attr('rx', 3)
        .style('cursor', 'pointer')
        .on('click', function(event, d) {
          event.stopPropagation();
          // If clicking a different node, hide old tooltip first
          const nodeId = d.elementId || d.id;
          if (activeTooltipNodeRef.current && activeTooltipNodeRef.current !== nodeId) {
            hideAllTooltips();
          }
          activeTooltipNodeRef.current = nodeId;

          d3.select(this)
            .attr('fill', '#f1f3f4')
            .attr('stroke', '#6c757d')
            .attr('stroke-width', 1);

          // Show tooltip with all properties
          d3.select(tooltipRef.current).style('z-index', 12).style('display', 'block').style('pointer-events', 'auto');
          d3.select(tooltipRef.current).style('opacity', 0.9);

          const nodeType = (d.labels && d.labels.length > 0) ? d.labels[0] : 'Node';
          // Handle both nested and flat structure
          const props = d.properties && typeof d.properties === 'object' && !Array.isArray(d.properties)
            ? d.properties
            : d;

          // HEADER: Show the node type with a drag handle and dock/close controls
          let tooltipContent = `
            <div class="dt-tooltip-header">
              <div class="dt-tooltip-handle" title="Drag to move">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="opacity:0.95;color:#fff"><rect x="3" y="5" width="4" height="2" rx="1" fill="currentColor"></rect><rect x="3" y="11" width="4" height="2" rx="1" fill="currentColor"></rect><rect x="3" y="17" width="4" height="2" rx="1" fill="currentColor"></rect></svg>
                <span style="font-weight:700;font-size:13px;margin-left:6px">${escapeHtml(nodeType)}</span>
              </div>
              <div style="display:flex;gap:8px;align-items:center">
                <button class="dt-dock-btn" aria-pressed="true">Dock</button>
                ${tooltipCloseBtn}
              </div>
            </div>
          `;
          // Recommendation action buttons (top, right after header)
          tooltipContent += buildRecActionBar(d);

          // Only exclude D3/graph-library internals — ALL real Neo4j properties will be shown
          const excludedProps = [
            'x', 'y', 'vx', 'vy', 'fx', 'fy', 'index',              // D3 force layout
            'depth', 'parent', 'data', 'height', 'level', 'children', // D3 tree layout
            'elementId', 'elementID', 'identity', 'labels', 'properties', '__typename', // driver metadata
          ];

          // Get all enumerable own properties
          const allProps = Object.keys(props)
            .filter(k => {
              if (excludedProps.includes(k)) return false;
              if (typeof props[k] === 'function') return false;
              return true;
            })
            .map(k => [k, props[k]]);

          // Show ALL properties from the API
          if (allProps.length > 0) {
            tooltipContent += `<div class="dt-tooltip-content" style="margin-top:8px; font-size:12px; max-height:300px;">`;
            allProps.forEach(([k, v]) => {
              // Format property key
              const formattedKey = escapeHtml(k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()));

              // Format value based on type
              let formattedValue = v;
              if (v === null || v === undefined) {
                formattedValue = '<em style="color: #95a5a6;">N/A</em>';
              } else if (typeof v === 'object') {
                formattedValue = escapeHtml(JSON.stringify(v));
              } else if (typeof v === 'boolean') {
                formattedValue = v ? '<span style="color: #27ae60; font-weight: bold;">' + CHAR_CHECK + ' Yes</span>' : '<span style="color: #e74c3c; font-weight: bold;">' + CHAR_CROSS + ' No</span>';
              } else {
                formattedValue = escapeHtml(String(v));
              }

              tooltipContent += `<div style="margin: 4px 0; padding: 4px 0; border-bottom: 1px solid #f0f0f0;">
                <strong style="color: #2c3e50;">${formattedKey}:</strong>
                <span style="color: #34495e; margin-left: 8px;">${formattedValue}</span>
              </div>`;
            });
            tooltipContent += `</div>`;
          } else {
            tooltipContent += `<div style="margin-top: 8px; padding: 12px; font-size: 12px; color: #95a5a6; font-style: italic; text-align: center;">No properties available</div>`;
          }

          // Apply smart positioning that respects viewport boundaries
          const tooltipEl = tooltipRef.current;
          if (tooltipEl && svgRef.current) {
            // Render tooltip as a fixed side panel (side menu) in the top-right corner of the canvas
            const svgRect = svgRef.current.getBoundingClientRect();
            const panelWidth = 340;
            const panelHeight = Math.max(100, svgRect.height);
            // Parent container (component root) rect
            const parentEl = svgRef.current.parentElement || svgRef.current.offsetParent;
            const parentRect = parentEl.getBoundingClientRect();

            // Compute coordinates relative to parent (for position:absolute)
            let panelTop = Math.max(0, Math.round(svgRect.top - parentRect.top));
            let panelLeft = Math.max(0, Math.round(svgRect.right - parentRect.left - panelWidth));

            // If SVG is narrower than panel, snap to parent's right edge
            if (svgRect.width < panelWidth) {
              panelLeft = Math.max(0, Math.round(svgRect.left - parentRect.left));
            }

            d3.select(tooltipEl)
              .html(tooltipContent)
              .style('position', 'absolute')
              .style('top', `${panelTop}px`)
              .style('left', `${panelLeft}px`)
              .style('right', 'unset')
              .style('width', `${panelWidth}px`)
              .style('height', `${panelHeight}px`)
              .style('overflowY', 'auto')
              .style('boxShadow', '0 2px 16px rgba(0,0,0,0.18)')
              .style('borderRadius', '10px 0 0 10px')
              .style('background', '#fff')
              .style('zIndex', 10000)
              .style('opacity', 1)
              .style('pointerEvents', 'auto')
              .attr('draggable', null)
              .on('mousedown.drag', null)
              .on('touchstart.drag', null);
            // Dock button and drag handle wiring
            const dockBtn = tooltipEl.querySelector('.dt-dock-btn');
            if (dockBtn) {
              // Initialize ARIA state
              dockBtn.setAttribute('aria-pressed', String(tooltipDockedRef.current));
              dockBtn.addEventListener('click', (ev) => {
                ev.stopPropagation();
                setTooltipDocked(prev => {
                  const next = !prev;
                  // After state update, reinitialize positioning or dragging
                  setTimeout(() => {
                    if (next) {
                      try { repositionTooltip(); } catch (e) {}
                    } else {
                      try { makeTooltipDraggable(tooltipEl); } catch (e) {}
                    }
                  }, 0);
                  return next;
                });
              });
            }

            // Initialize either docked positioning or draggable behavior
            if (tooltipDockedRef.current) {
              try { repositionTooltip(); } catch (e) { /* ignore */ }
            } else {
              try { makeTooltipDraggable(tooltipEl); } catch (e) { /* ignore */ }
            }
            // Attach close handler
            try { applyTooltipCloseHandler(tooltipEl); } catch (e) { /* ignore */ }
            try { wireTooltipRecButtons(tooltipEl, openTooltipRecommendation); } catch (e) { /* ignore */ }
          }
        });

      // Add indent lines
      rows.filter(d => d.level > 0)
        .append('line')
        .attr('x1', d => 35 + (d.level - 1) * indentWidth)
        .attr('y1', rowHeight / 2)
        .attr('x2', d => 35 + d.level * indentWidth - 10)
        .attr('y2', rowHeight / 2)
        .attr('stroke', '#ccc')
        .attr('stroke-width', 1);

      // Add vertical connecting lines
      rows.filter(d => d.level > 0)
        .append('line')
        .attr('x1', d => 35 + (d.level - 1) * indentWidth)
        .attr('y1', 0)
        .attr('x2', d => 35 + (d.level - 1) * indentWidth)
        .attr('y2', rowHeight / 2)
        .attr('stroke', '#ccc')
        .attr('stroke-width', 1);

      // Determine expandability sources
      const potentialSources = new Set();
      if (data.links && data.links.length > 0) {
        data.links.forEach(l => {
          const src = typeof l.source === 'object' ? (l.source.elementId || l.source.id || l.source.identity) : l.source;
          if (src) potentialSources.add(src);
        });
      } else if (fullDataset?.links?.length) {
        fullDataset.links.forEach(l => {
          const src = typeof l.source === 'object' ? (l.source.elementId || l.source.id || l.source.identity) : l.source;
          if (src) potentialSources.add(src);
        });
      }
      const expandable = rows.filter(d => (d.children && d.children.length > 0) || potentialSources.has(d.elementId));
      logger.render('[TreeLayout] Expandable row count:', expandable.size());

      // Triangle toggles removed - no more tree expansion triangles

      // Add node icons/circles - simple version without effects
      rows.append('circle')
        .attr('cx', d => 35 + d.level * indentWidth)
        .attr('cy', rowHeight / 2)
        .attr('r', nodeSize)
        .attr('fill', d => getNodeColor(d))
        .attr('stroke', '#fff')
        .attr('stroke-width', 1)
        .style('cursor', 'pointer')
        .on('mouseover', function(event, d) {
          d3.select(this)
            .attr('stroke-width', 1.6);
        })
        .on('mouseout', function(event, d) {
          d3.select(this)
            .attr('stroke-width', 1.2);
        });

      // Add node type badges with dynamic sizing based on text length
      rows.each(function(d) {
        const row = d3.select(this);
        const labelText = (d.labels && d.labels.length > 0) ? d.labels[0] : 'Unknown';

        // Create temporary text element to measure width
        const tempText = row.append('text')
          .attr('font-size', '10px')
          .attr('font-weight', 'bold')
          .text(labelText)
          .style('opacity', 0);

        const textWidth = tempText.node().getBBox().width;
        tempText.remove();

        // Calculate badge width (minimum 60px, add padding)
        const badgeWidth = Math.max(60, textWidth + 16);

        // Add badge rectangle with dynamic width
        row.append('rect')
          .attr('x', d => 55 + d.level * indentWidth)
          .attr('y', rowHeight / 2 - 8)
          .attr('width', badgeWidth)
          .attr('height', 16)
          .attr('rx', 8)
          .attr('fill', d => getNodeColor(d))
          .attr('fill-opacity', 0.15)
          .attr('stroke', d => getNodeColor(d))
          .attr('stroke-width', 1)
          .attr('class', 'tree-node-badge');

        // Add badge text with proper centering
        row.append('text')
          .attr('x', d => 55 + d.level * indentWidth + badgeWidth / 2)
          .attr('y', rowHeight / 2 + 3)
          .attr('text-anchor', 'middle')
          .attr('font-size', '10px')
          .attr('font-weight', 'bold')
          .attr('fill', d => getNodeColor(d))
          .text(labelText);
      });

      // Add API-based expand/collapse control for search mode (like force-directed graph)
      rows.filter(d => hasExpandableConnections(d) || canCollapseNode(d))
        .append('g')
        .attr('class', 'tree-api-expand')
        .attr('transform', d => `translate(${width - 60}, ${rowHeight / 2})`)
        .style('cursor', 'pointer')
        .on('click', async (event, d) => {
          event.stopPropagation();
          if (expandedNodesRef.current.has(d.elementId)) {
            collapseNode(d.elementId);
          } else if (hasExpandableConnections(d)) {
            // Expand the node and then rebuild tree hierarchy
            await expandNode(d.elementId);

            // Force update of tree expanded nodes to include the newly expanded node
            setTreeExpandedNodes(prev => {
              const newSet = new Set(prev);
              newSet.add(d.elementId);

              // Also expand parent path to ensure visibility
              const findParentPath = (nodeId, hierarchy, path = []) => {
                for (const root of hierarchy) {
                  const result = findNodePath(root, nodeId, [root.elementId]);
                  if (result) return result;
                }
                return [];
              };

              const findNodePath = (node, targetId, path) => {
                if (node.elementId === targetId) return path;
                if (node.children) {
                  for (const child of node.children) {
                    const result = findNodePath(child, targetId, [...path, child.elementId]);
                    if (result) return result;
                  }
                }
                return null;
              };

              // Expand the path to this node so it's visible
              const parentPath = findParentPath(d.elementId, hierarchicalData);
              parentPath.forEach(nodeId => newSet.add(nodeId));

              return newSet;
            });
          }
        })
        .each(function(d) {
          const g = d3.select(this);
          // Circle background
          g.append('circle')
            .attr('r', 10)
            .attr('fill', d => {
              if (canCollapseNode(d)) return '#868E96'; // Light grey for collapse
              if (hasExpandableConnections(d)) return '#6C757D'; // Medium grey for expand
              return 'transparent';
            })
            .attr('stroke', '#fff')
            .attr('stroke-width', 1)
          // Plus/Minus symbol
          g.append('text')
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'middle')
            .attr('font-size', '12px')
            .attr('font-weight', 'bold')
            .attr('fill', '#fff')
            .style('pointer-events', 'none')
            .text(d => {
              if (canCollapseNode(d)) return CHAR_MINUS; // Minus for collapse
              if (hasExpandableConnections(d)) return '+'; // Plus for expand
              return '';
            });
          // Loading indicator
          g.append('circle')
            .attr('r', 12)
            .attr('fill', 'none')
            .attr('stroke', '#6C757D')
            .attr('stroke-width', 1.2)
            .attr('stroke-dasharray', '3,3')
            .style('opacity', d => loadingNodes.has(d.elementId) ? 1 : 0)
            .style('pointer-events', 'none');
        });

      // Add main node labels with dynamic positioning and text wrapping
      rows.each(function(d) {
        const row = d3.select(this);
        const labelText = (d.labels && d.labels.length > 0) ? d.labels[0] : 'Unknown';

        // Calculate badge width to position main label correctly
        const tempText = row.append('text')
          .attr('font-size', '10px')
          .text(labelText)
          .style('opacity', 0);
        const badgeWidth = Math.max(60, tempText.node().getBBox().width + 16);
        tempText.remove();

        const mainLabelX = 65 + d.level * indentWidth + badgeWidth;
        // Show actual node name and version using schema-driven display
        const primaryLabel = getDisplayLabel(d);

        // const primaryLabel = props.Name || props.name || props.PartName || props.CADDocumentName;
        const mainText = row.append('text')
          .attr('x', mainLabelX)
          .attr('y', rowHeight / 2 - 2)
          .attr('font-size', '14px')
          .attr('font-weight', '600')
          .attr('fill', '#2C2C2C');

        // Simple text wrapping for very long labels
        if (primaryLabel.length > 30) {
          const words = primaryLabel.split(' ');
          let line = '';
          let lineNumber = 0;

          words.forEach(word => {
            const testLine = line + word + ' ';
            if (testLine.length > 25 && line !== '') {
              mainText.append('tspan')
                .attr('x', mainLabelX)
                .attr('dy', lineNumber === 0 ? 0 : '1.2em')
                .text(line.trim());
              line = word + ' ';
              lineNumber++;
            } else {
              line = testLine;
            }
          });

          // Add the last line
          if (line.trim() !== '') {
            mainText.append('tspan')
              .attr('x', mainLabelX)
              .attr('dy', lineNumber === 0 ? 0 : '1.2em')
              .text(line.trim());
          }
        } else {
          mainText.text(primaryLabel);
        }
      });

      // Subheading: show secondary identifiers (excluding version since it's now in main label)
      rows.each(function(d, i) {
        const row = d3.select(this);
        const labelText = (d.labels && d.labels.length > 0) ? d.labels[0] : 'Unknown';

        // Calculate badge width to position sublabel correctly
        const tempText = row.append('text')
          .attr('font-size', '10px')
          .text(labelText)
          .style('opacity', 0);
        const badgeWidth = Math.max(60, tempText.node().getBBox().width + 16);
        tempText.remove();

        const sublabelX = 65 + d.level * indentWidth + badgeWidth;

        row.append('text')
          .attr('class', 'tree-subheading')
          .attr('x', sublabelX)
          .attr('y', rowHeight / 2 + 12)
          .attr('font-size', '11px')
          .attr('fill', '#555')
          .text(() => {
            const p = d.properties || d;
            const main = getDisplayLabel(d) || '';

            // Secondary fields - show number, state, description (generic)
            const number = p.number || p.code || p.key;
            const state = p.state || p.status;
            const description = p.description;
            let stateVal = state && !main.toLowerCase().includes(String(state).toLowerCase()) ? state : undefined;

            const parts = [];
            if (number && !main.includes(number)) parts.push(number);
            if (stateVal) parts.push(stateVal);
            if (description && description.length < 30) parts.push(`"${description}"`);

            return parts.join(' ' + CHAR_BULLET + ' ');
          });
      });

      // Debug overlay removed (previous #tree-debug-fallback). Intentionally left blank.

      return rows;
    };

    // Initial render
    renderRows(scrollOffset);

    // Add scrolling if needed
    if (needsScrolling) {
      // Clear any previous wheel handler in case of multiple re-renders
      svg.on('wheel.tree-scroll', null);
      const maxScroll = Math.max(0, (flatNodes.length - maxVisibleRows) * rowHeight);

      // Add scroll event listener to the entire SVG
      svg.on('wheel', function(event) {
        event.preventDefault();
        const delta = event.deltaY;
        scrollOffset = Math.max(0, Math.min(maxScroll, scrollOffset + delta));
        renderRows(scrollOffset);
      });

      // Add scroll indicator
      const scrollIndicator = g.append('g')
        .attr('class', 'scroll-indicator')
        .attr('transform', `translate(${width - 35}, ${headerHeight + 10})`); // Moved 20px left from width-15 to width-35

      // Scroll bar background
      scrollIndicator.append('rect')
        .attr('width', 8)
        .attr('height', availableHeight - 20)
        .attr('fill', '#e0e0e0')
        .attr('rx', 4);

      // Scroll bar thumb
      const thumbHeight = Math.max(20, (maxVisibleRows / flatNodes.length) * (availableHeight - 20));
      const scrollThumb = scrollIndicator.append('rect')
        .attr('class', 'scroll-thumb')
        .attr('width', 8)
        .attr('height', thumbHeight)
        .attr('fill', '#999')
        .attr('rx', 4)
        .attr('y', 0)
        .style('cursor', 'pointer');

      // Add drag behavior to scroll thumb
      const drag = d3.drag()
        .on('start', function() {
          d3.select(this).attr('fill', '#666'); // Darker on drag
        })
        .on('drag', function(event) {
          const newY = Math.max(0, Math.min(availableHeight - 20 - thumbHeight, event.y));
          d3.select(this).attr('y', newY);

          // Calculate corresponding scroll offset
          const scrollRatio = newY / (availableHeight - 20 - thumbHeight);
          scrollOffset = scrollRatio * maxScroll;
          renderRows(scrollOffset);
        })
        .on('end', function() {
          d3.select(this).attr('fill', '#999'); // Reset color
        });

      scrollThumb.call(drag);

      // Update scroll thumb position
      const updateScrollThumb = () => {
        const thumbPosition = (scrollOffset / maxScroll) * (availableHeight - 20 - thumbHeight);
        scrollIndicator.select('.scroll-thumb')
          .attr('y', thumbPosition);
      };

      updateScrollThumb();

      // Update scroll on wheel events
      svg.on('wheel.tree-scroll', function(event) {
        event.preventDefault();
        const delta = event.deltaY;
        scrollOffset = Math.max(0, Math.min(maxScroll, scrollOffset + delta));
        renderRows(scrollOffset);
        updateScrollThumb();
      });
    }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [createHierarchicalData, tooltipRef, treeExpandedNodes, fullDataset, getDisplayLabel]);

  // Effect to handle tree layout updates when data changes from expansions
  useEffect(() => {
    if (layoutType === 'indented-tree' && expandedNodesRef.current.size > 0) {
      logger.render('[TreeLayout] Data changed with expanded nodes, updating tree state');

      // When data changes due to expansions, ensure the tree expanded state includes
      // all nodes that should be visible based on the new hierarchy
      const currentData = filteredData.nodes.length > 0 ? filteredData : fullDataset;
      if (currentData && currentData.nodes && currentData.links) {
        const newHierarchy = createHierarchicalData(currentData.nodes, currentData.links);

        // Auto-expand nodes that have children and are part of expansions
        const newTreeExpanded = new Set(treeExpandedNodes);

        const addExpandedChildren = (node) => {
          if (expandedNodesRef.current.has(node.elementId) && node.children && node.children.length > 0) {
            newTreeExpanded.add(node.elementId);
            node.children.forEach(addExpandedChildren);
          }
        };

        newHierarchy.forEach(addExpandedChildren);

        if (newTreeExpanded.size !== treeExpandedNodes.size) {
          setTreeExpandedNodes(newTreeExpanded);
        }
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandedNodes, layoutType, treeExpandedNodes]);

  // Note: link_color is now handled by getLinkColor() function defined earlier

  // Function to process links and add offset information for bidirectional relationships
  const processLinksForOffset = (links) => {
    // First, filter out HAS_PARENT links when there's a corresponding HAS_CHILD link
    const filteredLinks = [];
    const hasChildPairs = new Set();

    // First pass: identify all HAS_CHILD relationships
    links.forEach(link => {
      if (link.type === 'HAS_CHILD') {
        const sourceId = getLinkEndpointId(link.source);
        const targetId = getLinkEndpointId(link.target);
        const pairKey = [sourceId, targetId].sort().join('-');
        hasChildPairs.add(pairKey);
      }
    });

    // Second pass: filter out HAS_PARENT if HAS_CHILD exists for the same node pair
    links.forEach(link => {
      if (link.type === 'HAS_PARENT') {
        const sourceId = getLinkEndpointId(link.source);
        const targetId = getLinkEndpointId(link.target);
        const pairKey = [sourceId, targetId].sort().join('-');

        // Skip HAS_PARENT if HAS_CHILD exists for the same node pair
        if (hasChildPairs.has(pairKey)) {
          logger.render('Filtering out HAS_PARENT link as HAS_CHILD exists for the same node pair:', pairKey);
          return; // Skip this link
        }
      }
      filteredLinks.push(link);
    });

    // Group links by node pairs (regardless of direction)
    const linkPairs = new Map();

    filteredLinks.forEach(link => {
      // Create a consistent key for node pairs (sorted to handle both directions)
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      const pairKey = [sourceId, targetId].sort().join('-');

      if (!linkPairs.has(pairKey)) {
        linkPairs.set(pairKey, []);
      }
      linkPairs.get(pairKey).push(link);
    });

    // Add offset information to links that have multiple relationships
    linkPairs.forEach(pairLinks => {
      if (pairLinks.length > 1) {
        // Multiple links between same nodes - add offset info
        pairLinks.forEach((link, index) => {
          link.isOffset = true;
          link.offsetIndex = index;
          link.totalOffsets = pairLinks.length;
        });
      } else {
        // Single link - no offset needed
        pairLinks[0].isOffset = false;
      }
    });

    return filteredLinks;
  };

  // Function to calculate curved path for bidirectional links
  const calculateCurvedPath = (link, sourceX, sourceY, targetX, targetY) => {
    if (!link.isOffset || link.totalOffsets <= 1) {
      // Single direction link - use straight line
      return `M${sourceX},${sourceY}L${targetX},${targetY}`;
    }

    // Calculate curve parameters for bidirectional links
    const dx = targetX - sourceX;
    const dy = targetY - sourceY;
    const length = Math.sqrt(dx * dx + dy * dy);

    if (length === 0) return `M${sourceX},${sourceY}L${targetX},${targetY}`;

    // Perpendicular unit vector for curve direction
    const perpX = -dy / length;
    const perpY = dx / length;

    // Calculate curve offset - ensure opposite directions for bidirectional links
    const baseOffset = Math.max(50, length * 0.2); // Larger base offset for more visible curves

    // Create consistent curve direction based on link direction and offset index
    // For bidirectional links, we want them to curve in opposite directions
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);

    // Use source and target IDs to determine consistent curve direction
    const linkDirection = sourceId < targetId ? 1 : -1;
    const offsetDirection = link.offsetIndex % 2 === 0 ? 1 : -1;
    const curveDirection = linkDirection * offsetDirection;

    const offsetMultiplier = Math.floor(link.offsetIndex / 2) + 1; // Increase curve for multiple pairs
    const curveOffset = baseOffset * offsetMultiplier * curveDirection;

    // Calculate control point for quadratic curve
    const midX = (sourceX + targetX) / 2;
    const midY = (sourceY + targetY) / 2;
    const controlX = midX + perpX * curveOffset;
    const controlY = midY + perpY * curveOffset;

    // Return quadratic curve path
    return `M${sourceX},${sourceY}Q${controlX},${controlY} ${targetX},${targetY}`;
  };


  // --- D3 Drag Handlers (useCallback for stability, tied to simulation) ---
  const dragstarted = useCallback((event, d) => {
    if (!event.active) simulationRef.current?.alphaTarget(ALPHA_TARGET_DRAG).restart();
    d.fx = d.x;
    d.fy = d.y;
  }, []);

  const dragged = useCallback((event, d) => {
    d.fx = event.x;
    d.fy = event.y;
  }, []);

  const dragended = useCallback((event, d) => {
    if (!event.active) simulationRef.current?.alphaTarget(ALPHA_TARGET_END);
    d.fx = null;
    d.fy = null;
  }, []);

  const handleZoom = useCallback(({ transform }) => {
    userInteractedWithGraphRef.current = true;
    if (gRef.current) {
      gRef.current.attr('transform', transform);
    }
  }, []);

  // Performance: Optimized data fetching with caching and error handling
  useEffect(() => {
    let cancelled = false;
    const abortController = new AbortController();

    const fetchData = async () => {
      performanceLog('[SYNC] Starting data fetch from API...');
      if (!cancelled) {
        setIsLoading(true);
        setError(null);
      }

      try {
        performanceLog('[API] Loading graph overview...');
        let response;
        try {
          response = await apiClient.get(API.graph.graphView, {
            params: { limit: DEFAULT_GRAPH_OVERVIEW_LIMIT },
            signal: abortController.signal,
          });
        } catch (primaryError) {
          logger.warn('[GRAPH] Falling back to legacy /graphvis endpoint', primaryError);
          response = await apiClient.get(API.graph.graphvis, { signal: abortController.signal });
        }

        const dataSet = normalizeGraphDataset(response.data);
        performanceLog('[DATA] Graph overview received:', {
          status: response.status,
          nodeCount: dataSet.nodes.length,
          linkCount: dataSet.links.length,
        });

        if (dataSet.nodes.length > 0) {
          logger.render(`[OK] Data processed successfully: ${dataSet.nodes.length} nodes, ${dataSet.links.length} links`);
          if (!cancelled) {
            startTransition(() => {
              commitGraphSlice(dataSet, {
                updateGraphData: true,
                updateFullDataset: true,
                updateSearchResultData: true,
                syncResults: true,
              });
              setInitialData(dataSet);
            });
          }
        } else {
          logger.render('[WARN] Graph overview returned no nodes');
        }

        if (!cancelled) {
          setIsLoading(false);
        }
      } catch (err) {
        if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED' || cancelled) {
          return;
        }
        logger.error('[ERROR] Data Fetch Error:', err);
        logger.error('Error details:', {
          message: err.message,
          response: err.response?.data,
          status: err.response?.status
        });
        if (!cancelled) {
          setError(`Failed to load graph data: ${err.message}`);
          setIsLoading(false);
        }
      }

 };

  fetchData();
  return () => {
    cancelled = true;
    abortController.abort();
  };
// eslint-disable-next-line react-hooks/exhaustive-deps
}, []);

  // Monitor Neo4j connection health and refresh graph if reconnected
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await apiClient.get(API.graph.neo4jHealth);
        const connected = response.data?.neo4j_connected === true;
        const previousConnected = lastNeo4jConnectedRef.current;
        lastNeo4jConnectedRef.current = connected;

        if (
          connected &&
          previousConnected === false &&
          graphData.nodes.length === 0 &&
          !searchQuery &&
          !graphSearchActiveRef.current &&
          !userInteractedWithGraphRef.current &&
          graphViewModeRef.current === 'ontology' &&
          selectedOntologyRef.current === 'ALL'
        ) {
          // Connection was restored but graph is empty - trigger refresh
          logger.data('Neo4j reconnected, refreshing graph...');
          const graphResponse = await apiClient.get(API.graph.graphView, {
            params: { limit: DEFAULT_GRAPH_OVERVIEW_LIMIT },
          });
          const dataSet = normalizeGraphDataset(graphResponse.data);
          if (dataSet.nodes.length > 0) {
            startTransition(() => {
              commitGraphSlice(dataSet, {
                updateGraphData: true,
                updateFullDataset: true,
                updateSearchResultData: true,
                syncResults: true,
              });
            });
          }
        }
      } catch (err) {
        logger.warn('Health check error:', err.message);
      }
    };

    // Check health every 30 seconds
    const healthCheckInterval = setInterval(checkHealth, 30000);
    return () => clearInterval(healthCheckInterval);
  }, [commitGraphSlice, graphData.nodes.length, searchQuery, setData]);


  // Performance: Optimized search with debouncing and caching
  useEffect(() => {
    const isContextualQuery = graphViewModeRef.current === 'individual';

    if (!debouncedSearchQuery) {
      searchModeRef.current = false;
      setSearchLoading(false);
      setContextualSearchResults([]);
      setHighlightedNodeIds(new Set());
      setActiveSearchResultId(null);
      activeSearchResultIdRef.current = null;

      if (isContextualQuery) {
        setContextualRootNodeId(null);
        setSearchResultData({ nodes: [], links: [] });
        commitGraphSlice({ nodes: [], links: [] }, {
          updateFilteredData: true,
          updateGraphData: false,
          updateSearchResultData: true,
          clearActiveSearchId: true,
        });
        syncSharedSearchResults([], { clear: true });
        return;
      }
      const baseData = resolveSearchBaseDataset();
      setSearchResultData({ nodes: [], links: [] });
      syncSharedSearchResults(baseData.nodes || []);
      setActiveSearchResultId(null);
      return;
    }

    // Cancel previous in-flight search request to prevent race conditions
    const abortController = new AbortController();

    if (isContextualQuery) {
      const requestId = ++contextualSearchRequestIdRef.current;
      searchModeRef.current = true;
      setSearchLoading(true);
      syncContextualHighlights(debouncedSearchQuery);
      syncSharedSearchResults([], { clear: true });

      const performContextualSearch = async () => {
        try {
          const ontologyPrefix = resolveOntologySearchPrefix(selectedOntologyRef.current);
          const response = await graphApi.getContextualSubgraph({
            search: debouncedSearchQuery,
            // Keep the backend search broad and object-centric; root context is
            // chosen client-side from the returned matches so it is based on
            // actual Neo4j hits instead of a premature server-side root guess.
            limit: 24,
            ...(ontologyPrefix ? { ontology_prefix: ontologyPrefix } : {}),
            search_mode: 'broader',
            expand_neighbors: false,
          }, abortController.signal);

          if (requestId !== contextualSearchRequestIdRef.current) {
            return;
          }

          const normalized = normalizeGraphDataset(response.data);
          const candidateNodes = normalized.nodes.filter((node) => (
            node?.elementId
            && !isMetadataWrapperNode(node)
            && !isSchemaTerminalNode(node)
          ));
          const rankedMatches = nodeSearchFunction(candidateNodes, debouncedSearchQuery);
          await loadContextualSearchMatch(rankedMatches, debouncedSearchQuery, requestId, normalized);
        } catch (err) {
          if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
          logger.error('[CONTEXTUAL SEARCH] Error:', err);
          const visibleMatches = nodeSearchFunction(filteredDataRef.current?.nodes || [], debouncedSearchQuery);
          if (requestId === contextualSearchRequestIdRef.current) {
            await loadContextualSearchMatch(visibleMatches, debouncedSearchQuery, requestId, filteredDataRef.current);
          }
        }
      };

      performContextualSearch();
      return () => abortController.abort();
    }

    const performSearch = async () => {
      performanceLog('[SEARCH] Starting search for:', debouncedSearchQuery);
      searchModeRef.current = true;
      setSearchLoading(true);
      setLoadingNodes(new Set());
      syncSharedSearchResults([], { clear: true });
      startTransition(() => {
        setSearchResultData({ nodes: [], links: [] });
        setActiveSearchResultId(null);
      });
      const baseData = resolveSearchBaseDataset();

      try {
        const normalized = buildSearchResultSlice(baseData, debouncedSearchQuery, searchResultMode);

        performanceLog(
          '[SEARCH] Search API response:',
          normalized.nodes.length,
          isOntologyGraphMode ? 'ontology view nodes' : (isFullGraphMode ? 'full graph nodes' : 'focused nodes')
        );

        const searchAnchorId = findBestSearchMatchId(normalized.nodes, debouncedSearchQuery);
        const searchAnchorNode = searchAnchorId
          ? normalized.nodes.find((node) => node.elementId === searchAnchorId)
          : (normalized.nodes[0] || null);
        const orderedNodes = searchAnchorNode
          ? [searchAnchorNode, ...normalized.nodes.filter((node) => node.elementId !== searchAnchorNode.elementId)]
          : normalized.nodes;

        // Process search results directly without setting intermediate result state
        if (normalized.nodes.length > 0) {
          const nodes = orderedNodes;
          const validatedLinks = normalized.links;

          logger.render('[SEARCH] Search processed:', nodes.length, 'nodes,', validatedLinks.length, 'links');

          // For search results, REPLACE existing data instead of merging
          // This prevents contamination from previous searches or expansions
          let finalNodes = nodes;
          let finalLinks = validatedLinks;

          // Batch search result updates for better performance
        startTransition(() => {
          const searchGraph = { nodes: finalNodes, links: finalLinks };
          const currentActiveId = activeSearchResultIdRef.current;
          const bestMatchId = findBestSearchMatchId(finalNodes, debouncedSearchQuery);
          const nextActiveId = finalNodes.some((node) => node.elementId === currentActiveId)
            ? currentActiveId
            : bestMatchId;
          if (isContextualQuery) {
            setContextualRootNodeId(nextActiveId || finalNodes[0]?.elementId || null);
          }
          commitGraphSlice(searchGraph, {
            updateFilteredData: isContextualQuery,
            updateSearchResultData: true,
            nextActiveSearchId: nextActiveId,
            resetCenteredSearch: true,
            syncResults: true,
            forceSearchResults: true,
          });
        });
        } else {
        // Batch no results updates
        startTransition(() => {
          if (isContextualQuery) {
            setContextualRootNodeId(null);
          }
          commitGraphSlice({ nodes: [], links: [] }, {
            updateFilteredData: isContextualQuery,
            updateSearchResultData: true,
            clearActiveSearchId: true,
            syncResults: true,
            forceSearchResults: true,
          });
        });
        }

        // Batch loading state updates
        startTransition(() => {
          setSearchLoading(false);
        });
      } catch (err) {
        // Ignore cancelled requests (superseded by newer search)
        if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
        logger.error('Search Error:', err);
        const fallbackGraph = buildSearchResultSlice(resolveSearchBaseDataset(), debouncedSearchQuery, searchResultMode);
        // Batch fallback search updates
        startTransition(() => {
          const currentActiveId = activeSearchResultIdRef.current;
          const bestMatchId = findBestSearchMatchId(fallbackGraph.nodes, debouncedSearchQuery);
          const nextActiveId = fallbackGraph.nodes.some((node) => node.elementId === currentActiveId)
            ? currentActiveId
            : bestMatchId;
          if (isContextualQuery) {
            setContextualRootNodeId(nextActiveId || fallbackGraph.nodes[0]?.elementId || null);
          }
          commitGraphSlice(fallbackGraph, {
            updateFilteredData: isContextualQuery,
            updateSearchResultData: true,
            nextActiveSearchId: nextActiveId,
            resetCenteredSearch: true,
            syncResults: true,
            forceSearchResults: true,
          });
          setSearchLoading(false);
        });
      }
    };

    performSearch();
    // Cleanup: abort in-flight request when query changes or component unmounts
    return () => abortController.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildSearchResultSlice, commitGraphSlice, debouncedSearchQuery, graphViewMode, isFullGraphMode, isOntologyGraphMode, resolveSearchBaseDataset, searchResultMode]);

  // ── Ontology viewer: fetch ontology graph when dropdown changes ─────────
  const fetchOntologyGraph = useCallback(async (ontologyType, partName) => {
    if (ontologyType === 'ALL') {
      // Reset to initial full graph
      setOntologyGraphMessage('');
      commitGraphSlice(initialData, {
        updateGraphData: true,
        updateFullDataset: true,
        updateSearchResultData: true,
        syncResults: !searchModeRef.current,
      });
      setStepParts([]);
      setSelectedStepPart('ALL');
      return;
    }

    setOntologyLoading(true);
    setOntologyGraphMessage('');
    try {
      let response;
      if (ontologyType === 'step' && partName && partName !== 'ALL') {
        const endpointPath = replaceParams(API.graph.ontologyStepPart, { part: encodeURIComponent(partName) });
        response = await apiClient.get(endpointPath);
      } else if (ontologyType.endsWith('_instances')) {
        // pattern: 'ap242_instances' -> call instances endpoint for 'ap242'
        const base = ontologyType.replace(/_instances$/, '');
        response = await apiClient.get(
          buildUrl(replaceParams(API.graph.ontologyInstances, { ontology: base })),
          { params: { include_rels: true, limit: 1000 } }
        );
      } else if (ontologyType === 'mbse_instances') {
        response = await apiClient.get(API.graph.ontologyMbseInstances);
      } else {
        try {
          response = await graphApi.getOntologyGraph(ontologyType, DEFAULT_ONTOLOGY_VIEW_LIMIT);
        } catch (primaryError) {
          logger.warn('[ONTOLOGY] Falling back to legacy ontology graph endpoint', primaryError);
          const legacyEndpointPath = replaceParams(API.graph.graphvisByOntology, { prefix: ontologyType });
          response = await apiClient.get(legacyEndpointPath);
        }
      }
      const dataSet = normalizeGraphDataset(response.data);
      if (dataSet.nodes.length > 0) {
        const existingNodeIds = new Set(dataSet.nodes.map(node => node.elementId));
        const sampleLinks = dataSet.links.slice(0, 2);
        logger.ontology('[ONTOLOGY] Graph payload sample', {
          nodes: dataSet.nodes.slice(0, 2).map(n => ({ elementId: n.elementId, label: n.label })),
          nodeCount: dataSet.nodes.length,
          rawLinkCount: dataSet.links.length,
          links: sampleLinks.map(l => ({
          source: l.source,
          target: l.target,
          sourceExists: existingNodeIds.has(l.source),
          targetExists: existingNodeIds.has(l.target)
          })),
        });

        logger.ontology('[ONTOLOGY] Validated graph links', dataSet.links.length);
        if (dataSet.nodes.length > 0 && dataSet.links.length === 0 && response.data?.results?.length > 0) {
          setOntologyGraphMessage('Ontology has relationships, but visualization could not match relationship source/target IDs.');
        } else if (dataSet.nodes.length > 0 && dataSet.links.length === 0) {
          setOntologyGraphMessage('Ontology has classes but no relationships.');
        } else {
          setOntologyGraphMessage('');
        }
        commitGraphSlice(dataSet, {
          updateGraphData: true,
          updateFullDataset: true,
          updateSearchResultData: true,
          syncResults: !searchModeRef.current,
        });
        logger.render(`[ONTOLOGY] Loaded ${ontologyType}: ${dataSet.nodes.length} nodes, ${dataSet.links.length} links`);
      } else {
        const empty = { nodes: [], links: [] };
        setOntologyGraphMessage(response.data?.message || response.data?.error || 'Selected ontology scope returned no graph records.');
        commitGraphSlice(empty, {
          updateGraphData: true,
          updateFullDataset: true,
          updateSearchResultData: true,
          syncResults: !searchModeRef.current,
        });
      }
    } catch (err) {
      logger.error('[ONTOLOGY] Fetch error:', err);
      setOntologyGraphMessage(err?.response?.data?.detail || err?.message || 'Visualization received empty graph.');
    } finally {
      setOntologyLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialData]);

  // Ontology options are now loaded from centralized OntologyContext
  // This eliminates duplicate polling and API calls across components

  // Keep selectedOntologyRef in sync so graphViewMode effect can read latest value without stale closure
  useEffect(() => { selectedOntologyRef.current = selectedOntology; }, [selectedOntology]);
  useEffect(() => {
    if (selectedOntology && selectedOntology !== 'ALL') {
      lastSpecificOntologyRef.current = selectedOntology;
    }
  }, [selectedOntology]);

  useEffect(() => {
    if (graphViewMode !== 'individual') {
      setContextualSearchResults([]);
      setHighlightedNodeIds(new Set());
      return;
    }
    if (!debouncedSearchQuery) {
      setHighlightedNodeIds(new Set());
      return;
    }
    syncContextualHighlights(debouncedSearchQuery);
  }, [debouncedSearchQuery, filteredData, graphViewMode, syncContextualHighlights]);

  // When graph view mode switches, load the appropriate dataset
  useEffect(() => {
    graphViewModeRef.current = graphViewMode;
    resetGraphSelectionState({
      resetOntology: false,
      resetStepPart: false,
      resetSearch: false,
      resetExpansion: true,
      resetInteraction: false,
    });
    if (graphSearchActive) {
      syncSharedSearchResults([], { clear: true });
    }

    if (graphViewMode === 'individual') {
      const currentRootId = contextualRootNodeIdRef.current;
      const currentContext = filteredDataRef.current;
      const hasVisibleRoot = Boolean(
        currentRootId
        && Array.isArray(currentContext?.nodes)
        && currentContext.nodes.some((node) => node?.elementId === currentRootId)
      );

      if (hasVisibleRoot && (currentContext?.nodes?.length || 0) > 0) {
        startTransition(() => {
          commitGraphSlice(currentContext, {
            updateGraphData: false,
            updateSearchResultData: false,
          });
        });
      } else {
        const nextRootId = resolveContextualEntryNodeId();
        if (nextRootId) {
          loadContextualRootGraph(nextRootId, { preserveSearch: true });
          return;
        }
        const emptyContext = { nodes: [], links: [] };
        setContextualRootNodeId(null);
        startTransition(() => {
          commitGraphSlice(emptyContext, {
            updateGraphData: false,
            updateSearchResultData: false,
            clearActiveSearchId: true,
          });
        });
      }
      if (!searchModeRef.current) setTimeout(() => syncSharedSearchResults([], { clear: true }), 0);
    } else {
      // Ontology mode — restore or refetch based on active ontology selection.
      const selected = selectedOntologyRef.current || 'ALL';
      if (selected === 'ALL') {
        startTransition(() => {
          commitGraphSlice(initialData, {
            updateGraphData: true,
            updateFullDataset: true,
            updateSearchResultData: true,
            syncResults: !searchModeRef.current,
          });
        });
        if (!searchModeRef.current) setTimeout(() => syncSharedSearchResults(initialData.nodes), 0);
      } else {
        // Force refresh since selectedOntology effect does not run on graphViewMode changes.
        const part = selected === 'step' ? selectedStepPart : 'ALL';
        fetchOntologyGraph(selected, part);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphViewMode, commitGraphSlice, resetGraphSelectionState, syncSharedSearchResults]);

  // Keep Individual view in sync when fresh initial graph data arrives.
  useEffect(() => {
    if (graphViewModeRef.current !== 'individual') return;
    if (contextualRootNodeIdRef.current) {
      loadContextualRootGraph(contextualRootNodeIdRef.current, { preserveSearch: true });
      return;
    }
    const emptyContext = { nodes: [], links: [] };
    startTransition(() => {
      commitGraphSlice(emptyContext, {
        updateGraphData: false,
        updateSearchResultData: false,
        clearActiveSearchId: true,
      });
    });
    if (!searchModeRef.current) setTimeout(() => syncSharedSearchResults([], { clear: true }), 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialData, commitGraphSlice, loadContextualRootGraph, syncSharedSearchResults]);

  // When ontology selection changes, fetch graph and optionally fetch STEP parts
  useEffect(() => {
    if (graphViewModeRef.current === 'individual') return; // individual mode manages its own data
    // Clear search state when switching ontology
    resetGraphSelectionState({ resetOntology: false, resetStepPart: false });

    if (selectedOntology === 'step') {
      // Fetch STEP parts list for secondary filter
      setStepPartsLoading(true);
      setStepPartsError(null);
      graphApi.getStepParts()
        .then(res => {
          const parts = res.data?.parts || [];
          setStepParts(parts);
          setSelectedStepPart('ALL');
          if (parts.length === 0) {
            setStepPartsError('No STEP parts available');
          }
        })
        .catch(err => {
          const errorMsg = err.response?.data?.detail || err.message || 'Failed to fetch STEP parts';
          setStepPartsError(errorMsg);
          logger.error('[ONTOLOGY] Failed to fetch STEP parts:', err);
        })
        .finally(() => setStepPartsLoading(false));
    } else {
      setStepParts([]);
      setSelectedStepPart('ALL');
      setStepPartsError(null);
    }

    fetchOntologyGraph(selectedOntology, 'ALL');
  }, [selectedOntology, fetchOntologyGraph, resetGraphSelectionState]);

  // When STEP part sub-filter changes, fetch that specific part's graph
  useEffect(() => {
    if (graphViewModeRef.current === 'individual') return;
    if (selectedOntology !== 'step') return;
    // Skip if 'ALL' — the main ontology useEffect already handles that
    if (selectedStepPart === 'ALL') return;
    fetchOntologyGraph('step', selectedStepPart);
  }, [selectedStepPart, selectedOntology, fetchOntologyGraph]);

  // Function to determine if a node has expandable connections
  const hasExpandableConnections = (nodeData) => {
    // Allow expansion in contextual-instance mode even without an active search.
    const isNotExpanded = !expandedNodesRef.current.has(nodeData.elementId);
    const hasSearchQuery = !!debouncedSearchQueryRef.current;
    const isContextualMode = graphViewModeRef.current === 'individual';
    const backendTraversalHint = nodeData?.can_traverse ?? nodeData?.properties?.can_traverse;
    const nodeId = nodeData?.elementId;
    const currentSlice = getCurrentGraphSlice();
    const visibleLinks = Array.isArray(currentSlice?.links) && currentSlice.links.length > 0
      ? currentSlice.links
      : (Array.isArray(filteredData?.links) && filteredData.links.length > 0
        ? filteredData.links
        : (Array.isArray(graphData?.links) ? graphData.links : []));
    const hasVisibleConnections = visibleLinks.some((link) => {
      const sourceId = getLinkEndpointId(link?.source);
      const targetId = getLinkEndpointId(link?.target);
      return sourceId === nodeId || targetId === nodeId;
    });
    const isTraversalSupported = typeof backendTraversalHint === 'boolean'
      ? backendTraversalHint
      : (!isSchemaTerminalNode(nodeData) && (isIndividualTraversalNode(nodeData) || hasVisibleConnections || isContextualMode));

    return (hasSearchQuery || isContextualMode) && isNotExpanded && isTraversalSupported;
  };

  // Function to determine if a node can be collapsed
  const canCollapseNode = (nodeData) => {
    // Allow collapse in contextual-instance mode and search mode.
    const isExpanded = expandedNodesRef.current.has(nodeData.elementId);
    const hasSearchQuery = !!debouncedSearchQueryRef.current; // Use live debounced search state
    const isContextualMode = graphViewModeRef.current === 'individual';

    return (hasSearchQuery || isContextualMode) && isExpanded;
  };

  // Function to expand a node using graphtraverse API - 1-2 hop expansion
  const expandNode = async (nodeId) => {
    if (expandedNodesRef.current.has(nodeId)) {
      return;
    }

    const currentData = getCurrentGraphSlice();
    const currentSearchQuery = debouncedSearchQueryRef.current;
    const isContextualMode = graphViewModeRef.current === 'individual';
    const hasVisibleContext = Array.isArray(currentData?.links) && currentData.links.length > 0;

    if (isContextualMode && !hasVisibleContext) {
      await loadContextualRootGraph(nodeId, { preserveSearch: true });
      return;
    }

    setLoadingNodes(prev => new Set([...prev, nodeId]));

    // Track nodes that will be added by this expansion
    const addedNodeIds = new Set();
    const addedLinkIds = new Set();

    try {
      const response = await graphApi.getTraversal(nodeId, 1);
      const traversalData = normalizeGraphDataset(response.data, {
        collapseHiddenBridges: graphViewModeRef.current === 'individual',
      });

      if (traversalData.nodes.length > 0) {
        const mergedData = mergeGraphData(currentData, traversalData);

        traversalData.nodes.forEach((node) => {
          if (!currentData.nodes.some((existing) => existing.elementId === node.elementId)) {
            addedNodeIds.add(node.elementId);
          }
        });

        traversalData.links.forEach((link) => {
          if (!currentData.links.some((existing) => existing.elementId === link.elementId)) {
            addedLinkIds.add(link.elementId);
          }
        });

        const finalNodes = mergedData.nodes;
        const finalLinks = mergedData.links;

        performanceLog('Two-hop expansion:', addedNodeIds.size, 'new nodes,', addedLinkIds.size, 'new links');

        const validated = deduplicateNodesAndLinks(finalNodes, finalLinks);
        const existingNodeIds = new Set(validated.nodes.map(node => node.elementId));
        const validatedLinks = validated.links.filter((link) => existingNodeIds.has(link.source) && existingNodeIds.has(link.target));
        const newData = { nodes: validated.nodes, links: validatedLinks };

        // Batch all state updates for better performance
        startTransition(() => {
          // Update the current filtered data (what's currently displayed)
          setFilteredData(newData);
          setData(newData);
          if (currentSearchQuery) {
            setSearchResultData(newData);
          }

          // ONLY update fullDataset if we're NOT in a search state
          // This prevents reverting to default nodes when expanding during search
          if (!currentSearchQuery) {
            setFullDataset(newData);
            setGraphData(newData);
          }

          // Update search results if search is active
          if (currentSearchQuery) syncSharedSearchResults(newData.nodes);

          if (setVisibleRelationships) {
            setVisibleRelationships(newData.links);
          }

          // Store which nodes and links were added by this expansion
          setNodeExpansions(prev => {
            const newMap = new Map([...prev, [nodeId, { addedNodeIds, addedLinkIds, level: 1 }]]);
            nodeExpansionsRef.current = newMap;
            return newMap;
          });

          setExpandedNodes(prev => {
            const newSet = new Set([...prev, nodeId]);
            expandedNodesRef.current = newSet;
            return newSet;
          });

        });
      } // End of if (response.data && response.data.results)
    } catch (error) {
      logger.error('Error expanding node:', nodeId, error);
    } finally {
      setLoadingNodes(prev => {
        const newSet = new Set(prev);
        newSet.delete(nodeId);
        return newSet;
      });
    }
  };

  // Function to collapse a node - removes only the nodes/links added by that expansion
  const collapseNode = (nodeId) => {
    logger.render('=== COLLAPSE FUNCTION START ===');
    logger.render('Collapsing node:', nodeId);
    logger.render('Current nodeExpansions:', Array.from(nodeExpansionsRef.current.entries()));
    logger.render('Current expandedNodes:', Array.from(expandedNodesRef.current));
    const currentData = getCurrentGraphSlice();
    logger.render('Current filteredData nodes:', currentData.nodes.map(n => n.elementId));

    // Get the expansion info for this node
    const expansionInfo = nodeExpansionsRef.current.get(nodeId);
    if (!expansionInfo) {
      logger.render('ERROR: No expansion info found for node:', nodeId);
      logger.render('Available expansions:', Array.from(nodeExpansionsRef.current.keys()));
      return;
    }

    const expansionEntries = Array.from(nodeExpansionsRef.current.entries());
    const descendantExpansionIds = new Set([nodeId]);
    const nodesToRemove = new Set(expansionInfo.addedNodeIds);
    const linksToRemove = new Set(expansionInfo.addedLinkIds);

    let foundDescendant = true;
    while (foundDescendant) {
      foundDescendant = false;
      for (const [expandedId, info] of expansionEntries) {
        if (descendantExpansionIds.has(expandedId)) continue;
        if (!nodesToRemove.has(expandedId)) continue;
        descendantExpansionIds.add(expandedId);
        info.addedNodeIds.forEach((addedId) => nodesToRemove.add(addedId));
        info.addedLinkIds.forEach((addedId) => linksToRemove.add(addedId));
        foundDescendant = true;
      }
    }

    logger.render('Nodes to remove:', Array.from(nodesToRemove));
    logger.render('Links to remove:', Array.from(linksToRemove));
    logger.render('Expanded branches to remove:', Array.from(descendantExpansionIds));

    // Debug: Check if the nodes to be removed are actually in the current data
    const currentNodeIds = new Set(currentData.nodes.map(n => n.elementId));
    const presentNodeIdsToRemove = Array.from(nodesToRemove).filter(id => currentNodeIds.has(id));
    logger.render('Nodes that will actually be removed (present in current data):', presentNodeIdsToRemove);

    // Remove the nodes and links that were added by this expansion using the
    // shared graph utility so pruning stays consistent across search / expand / collapse.
    const prunedData = removeExpandedSubgraph(
      currentData,
      Array.from(nodesToRemove),
      Array.from(linksToRemove)
    );

    const filteredNodes = prunedData.nodes;
    const filteredLinks = prunedData.links;

    logger.render('Nodes before collapse:', currentData.nodes.length, 'after:', filteredNodes.length);
    logger.render('Links before collapse:', currentData.links.length, 'after:', filteredLinks.length);
    logger.render('Remaining node IDs:', filteredNodes.map(n => n.elementId));

    // Validate that we're actually removing nodes
    if (filteredNodes.length === currentData.nodes.length && nodesToRemove.size > 0) {
      logger.warn('No visible nodes were removed during collapse. The removed slice may already be absent from the current graph state.');
      logger.warn('nodesToRemove:', Array.from(nodesToRemove));
      logger.warn('current node elementIds:', currentData.nodes.map(n => n.elementId));
    }

    // Update datasets
    const newData = deduplicateNodesAndLinks(filteredNodes, filteredLinks);
    logger.render('Setting new data:', {
      nodeCount: newData.nodes.length,
      linkCount: newData.links.length
    });

    const currentSearchQuery = debouncedSearchQueryRef.current;
    const nextActiveId = findBestSearchMatchId(newData.nodes, currentSearchQuery);
    commitGraphSlice(newData, {
      updateSearchResultData: true,
      nextActiveSearchId: nextActiveId,
      resetCenteredSearch: true,
      syncResults: true,
      forceSearchResults: !!currentSearchQuery,
    });

    // Mirror expand behavior: only replace the backing dataset when we are not
    // currently viewing a search-derived slice of the graph.
    if (!currentSearchQuery) {
      setFullDataset(newData);
      setGraphData(newData);
    }

    // Remove this node from expanded set and expansion tracking
    setExpandedNodes(prev => {
      const newSet = new Set(prev);
      descendantExpansionIds.forEach((expandedId) => newSet.delete(expandedId));
      expandedNodesRef.current = newSet;
      logger.render('Updated expandedNodes:', Array.from(newSet));
      return newSet;
    });

    setNodeExpansions(prev => {
      const newMap = new Map(prev);
      descendantExpansionIds.forEach((expandedId) => newMap.delete(expandedId));
      nodeExpansionsRef.current = newMap;
      logger.render('Updated nodeExpansions:', Array.from(newMap.entries()));
      return newMap;
    });

    logger.render('=== COLLAPSE FUNCTION END ===');
  };

  // Function to initialize node positions around center
  const initializeNodePositions = (nodes, width, height) => {
    const centerX = width / 2;
    const centerY = height / 2;

    nodes.forEach((node, index) => {
      if (!node.x && !node.y) {
        // Deterministic disk seed avoids the donut/ring effect caused by circular seeding.
        const angle = index * Math.PI * (3 - Math.sqrt(5));
        const radius = Math.sqrt((index + 1) / Math.max(1, nodes.length)) * Math.min(width, height) * 0.36;
        node.x = centerX + Math.cos(angle) * radius;
        node.y = centerY + Math.sin(angle) * radius;
      }
    });
  };


// Add boundary force to keep nodes within viewport
const boundaryForce = (width, height) => {
  let nodes;

  const force = (alpha) => {
    nodes.forEach(node => {
      const padding = VIEWPORT_PADDING;
      const strength = 0.1 * alpha;

      if (node.x < padding) {
        node.vx += (padding - node.x) * strength;
      } else if (node.x > width - padding) {
        node.vx += (width - padding - node.x) * strength;
      }

      if (node.y < padding) {
        node.vy += (padding - node.y) * strength;
      } else if (node.y > height - padding) {
        node.vy += (height - padding - node.y) * strength;
      }
    });
  };

  force.initialize = (_nodes) => { nodes = _nodes; };
  return force;
};



  // --- 3. D3 Initialization and Update (runs when filteredData/activeNode/handlers change) ---
  useEffect(() => {
    const startTime = performance.now();
    logger.render(`[RENDER] Starting render with ${filteredData.nodes?.length || 0} nodes, ${filteredData.links?.length || 0} links`);
    const svgElement = svgRef.current;
    if (!svgElement) {
      logger.warn('SVG ref is not available yet.');
      return undefined;
    }

    // Performance optimization: detect layout changes
    const layoutChanged = layoutType !== prevLayoutType;
    if (layoutChanged) {
      logger.render(`[SYNC] Layout changed from ${prevLayoutType} to ${layoutType}`);
      setPrevLayoutType(layoutType);
    }

    const svg = d3.select(svgElement);
    const width = svgElement.clientWidth || 800;
    const height = svgElement.clientHeight || 600;

    // Click on empty SVG background dismisses any open tooltip
    svg.on('click', function(event) {
      // Only if the click target is the SVG itself (not a node/link)
      if (event.target === svgRef.current) {
        hideAllTooltips();
      }
    });

    if (!gRef.current) {
      svg.selectAll('*').remove(); // Clear existing content on first render

      // Define Arrowhead Marker in SVG defs BEFORE creating main group
      const defs = svg.append("defs"); // Append defs directly to SVG

      Object.entries(RELATIONSHIP_THEME).forEach(([key, theme]) => {
        defs.append("marker")
          .attr("id", theme.markerId)
          .attr("viewBox", `0 -${ARROW_HEAD_WIDTH / 2} ${ARROW_HEAD_LENGTH} ${ARROW_HEAD_WIDTH}`)
          .attr("refX", ARROW_REF_X)
          .attr("refY", 0)
          .attr("markerWidth", ARROW_HEAD_LENGTH)
          .attr("markerHeight", ARROW_HEAD_WIDTH)
          .attr("orient", "auto")
          .append("path")
            .attr("d", `M0,-${ARROW_HEAD_WIDTH / 2}L${ARROW_HEAD_LENGTH},0L0,${ARROW_HEAD_WIDTH / 2}`)
            .attr("fill", theme.color);
      });

      logger.render('D3 Arrowhead Marker defined in defs');

      gRef.current = svg.append('g'); // Main group for graph elements
      if (!zoomBehaviorRef.current) {
        zoomBehaviorRef.current = d3.zoom()
          .scaleExtent([0.1, 5])
          .on('zoom', handleZoom);
      }
      svg.call(zoomBehaviorRef.current);

      logger.render('D3 SVG initialized with marker in persistent defs.');
    }

    // During search, never fall back to the full graph canvas.
    // That fallback makes the UI flash or stay on the full graph while a focused search result is loading.
    const hasData = graphSearchActive
      ? activeDisplayData.nodes.length > 0
      : (graphViewMode === 'individual'
        ? activeDisplayData.nodes.length > 0
        : (activeDisplayData.nodes.length > 0 || (graphData.nodes && graphData.nodes.length > 0)));
    const renderData = graphSearchActive
      ? (activeDisplayData.nodes.length > 0 ? activeDisplayData : { nodes: [], links: [] })
      : (graphViewMode === 'individual'
        ? (activeDisplayData.nodes.length > 0 ? activeDisplayData : { nodes: [], links: [] })
        : (activeDisplayData.nodes.length > 0 ? activeDisplayData :
            (graphData.nodes && graphData.nodes.length > 0) ? graphData :
            { nodes: [], links: [] }));
    const showNodeLabels = true;

    if (!hasData) {
      if (gRef.current) {
        gRef.current.selectAll('*').remove();  // Only clear graph content
      }
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
      logger.render('No nodes to display after filtering. Graph cleared.');
      return;
    }

    logger.render(`[DATA] Rendering with ${renderData.nodes.length} nodes, ${renderData.links.length} links`);

    if (renderData.links && renderData.links.length > 0) {
      const sample = renderData.links.slice(0, 2);
      logger.render('[RENDER] Sample links with source/target:', sample.map(l => ({
        elementId: l.elementId,
        source: l.source,
        target: l.target,
        type: l.type
      })));
    }

    // Performance warning for large graphs
    if (renderData.nodes.length > 500) {
      logger.warn(`[WARN] Large graph detected (${renderData.nodes.length} nodes). Performance may be affected.`);
    }

    // Check layout type and render accordingly
    if (layoutType === 'indented-tree') {
      // Stop any running simulation for tree layout
      if (simulationRef.current) {
        simulationRef.current.stop();
        simulationRef.current = null; // Clear the reference
      }
      // Clear any existing node count displays from force-directed layout
      svg.selectAll('.node-count-display').remove();
      // Clear only graph content, preserve defs
      if (gRef.current) {
        gRef.current.selectAll('*').remove();  // Only clear gRef content, not defs
      }
      // Render indented tree layout using the correct data
      logger.render(`[TREE] Rendering tree with ${renderData.nodes.length} nodes`);
      renderIndentedTree(renderData, svg, width, height);
      logger.render('Rendered Indented Tree Layout');
      return;
    }

    // Force-directed layout (original code)
    // Clear tree layout content and ensure proper group structure
    if (gRef.current) {
      gRef.current.selectAll('*').remove();  // Only clear graph content, not defs
    } else {
      gRef.current = svg.append('g');
    }

    // Clear any existing node count displays to prevent overlapping
    svg.selectAll('.node-count-display').remove();

    // Add simple node count display for force-directed graph
    svg.append('text')
      .attr('class', 'node-count-display')
      .attr('x', width - 20)
      .attr('y', 30)
      .attr('text-anchor', 'end')
      .attr('font-size', '14px')
      .attr('font-weight', 'bold')
      .attr('fill', TCS_GRAPH_THEME.primary)
      .attr('stroke', 'white')
      .attr('stroke-width', '1.4')
      .attr('paint-order', 'stroke fill')
      .text(`Nodes: ${renderData.nodes.length}`);

    // Re-enable zoom for force-directed layout
    if (!zoomBehaviorRef.current) {
      zoomBehaviorRef.current = d3.zoom()
        .scaleExtent([0.1, 5])
        .on('zoom', handleZoom);
    }
    svg.call(zoomBehaviorRef.current);

    logger.render(`[TARGET] Initializing graph layout with ${renderData.nodes.length} nodes, ${renderData.links.length} links`);

    // Initialize positions for new nodes (especially for search results)
    initializeNodePositions(renderData.nodes, width, height);

    // --- Process links for bidirectional relationship separation ---
    const renderNodeIds = new Set((renderData.nodes || []).map(node => node.elementId));
    const safeRenderLinks = (renderData.links || []).filter((link) => {
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      return renderNodeIds.has(sourceId) && renderNodeIds.has(targetId);
    });
    const processedLinks = processLinksForOffset([...safeRenderLinks]);

    logger.render('[LINK PROCESSING]', {
      inputLinks: renderData.links.length,
      safeLinks: safeRenderLinks.length,
      processedLinks: processedLinks.length,
      sample: processedLinks.slice(0, 2).map(l => ({ source: l.source, target: l.target, type: l.type }))
    });

    // --- Initialize/Update Simulation ---
    if (!simulationRef.current) {
      simulationRef.current = d3.forceSimulation(renderData.nodes)
        .force('link', d3.forceLink(processedLinks).id(d => d.elementId).distance((d) => {
          const relationshipType = typeof d === 'object' ? d.type : '';
          return relationshipType === 'SUBCLASS_OF' ? 145 : (relationshipType === 'DOMAIN' || relationshipType === 'RANGE' ? 130 : LINK_DISTANCE);
        }))
        .force('charge', d3.forceManyBody().strength(CHARGE_STRENGTH))
        .force('center', d3.forceCenter(width / 2, height / 2).strength(CENTER_FORCE_STRENGTH))
        .force('collide', d3.forceCollide().radius((d) => getNodeCollisionRadius(d, showNodeLabels)).iterations(renderData.nodes.length > 300 ? 1 : 2))
        .force('boundary', boundaryForce(width, height));

      // Performance optimization: reduce iterations for large graphs
      const nodeCount = renderData.nodes.length;
      if (nodeCount > 100) {
        simulationRef.current.alphaDecay(0.05); // Faster stabilization for large graphs
      }
      if (nodeCount > 200) {
        simulationRef.current.alphaDecay(0.08).velocityDecay(0.6); // Much faster for very large graphs
      }
      if (nodeCount > 300) {
        // For very large graphs, use even more aggressive optimization
        simulationRef.current
          .alphaDecay(0.1)
          .velocityDecay(0.7)
          .alpha(0.3); // Start with lower alpha
      }

      logger.render('D3 Simulation initialized with', nodeCount, 'nodes');
    } else {
      // Performance optimization: only update if data actually changed
      const currentNodes = simulationRef.current.nodes();
      const currentNodeIds = currentNodes.map(n => n.elementId).sort().join(',');
      const newNodeIds = renderData.nodes.map(n => n.elementId).sort().join(',');
      const nodesChanged = currentNodeIds !== newNodeIds;

      if (nodesChanged || layoutChanged) {
        // Update simulation data
        simulationRef.current.nodes(renderData.nodes);
        simulationRef.current.force('link').links(processedLinks);
        simulationRef.current.force('center', d3.forceCenter(width / 2, height / 2).strength(CENTER_FORCE_STRENGTH));
        simulationRef.current.force('collide', d3.forceCollide().radius((d) => getNodeCollisionRadius(d, showNodeLabels)).iterations(renderData.nodes.length > 300 ? 1 : 2));
        simulationRef.current.force('boundary', boundaryForce(width, height));

        // Use lower alpha for smoother transitions, higher for layout changes
        const alpha = layoutChanged ? 0.5 : 0.3;
        simulationRef.current.alpha(alpha).restart();
        logger.render(`D3 Simulation updated with alpha ${alpha} (nodes changed: ${nodesChanged}, layout changed: ${layoutChanged})`);
      } else {
        logger.render('Skipping simulation update - no data changes detected');
      }
    }

    const simulationLinks = simulationRef.current?.force('link')?.links?.() || processedLinks;
    const nodeById = new Map((renderData.nodes || []).map((node) => [node.elementId, node]));
    const resolveLinkNode = (endpoint) => {
      if (!endpoint) return null;
      if (typeof endpoint === 'object') return endpoint;
      return nodeById.get(endpoint) || null;
    };
    const renderLinkPath = (selection) => {
      selection.each(function(d) {
        const sourceNode = resolveLinkNode(d.source);
        const targetNode = resolveLinkNode(d.target);
        const sourceX = sourceNode?.x;
        const sourceY = sourceNode?.y;
        const targetX = targetNode?.x;
        const targetY = targetNode?.y;
        if (
          !Number.isFinite(sourceX)
          || !Number.isFinite(sourceY)
          || !Number.isFinite(targetX)
          || !Number.isFinite(targetY)
        ) {
          d3.select(this).attr('d', null);
          return;
        }
        const pathData = calculateCurvedPath(d, sourceX, sourceY, targetX, targetY);
        d3.select(this).attr('d', pathData);
      });
    };
    const renderNodePositions = (selection) => {
      selection.attr('transform', d => (
        Number.isFinite(d?.x) && Number.isFinite(d?.y)
          ? `translate(${d.x},${d.y})`
          : null
      ));
    };

    // --- D3 Data Binding and Drawing ---
    // Links (paths for curved bidirectional links, lines for single links)
    const link = gRef.current.selectAll('.link')
      .data(simulationLinks, d => d.elementId)
      .join(
        enter => {
          logger.render('[LINK] Creating new links with marker-end attribute', enter.size());
          const group = enter.append('path')
            .attr('class', 'link')
            .attr('stroke', d => getRelationshipVisual(d.type).color)
            .attr('stroke-opacity', LINK_OPACITY)
            .attr('stroke-width', d => getRelationshipVisual(d.type).width)
            .attr('stroke-dasharray', d => getRelationshipVisual(d.type).dasharray)
            .attr('fill', 'none')  // Important for path elements
            .attr('marker-end', d => `url(#${getRelationshipVisual(d.type).markerId})`)
            .on('click', function (event, d) {
              event.stopPropagation();
              // Hide node tooltip if showing, track this link
              const linkId = d.elementId || `${d.source}-${d.target}`;
              if (activeTooltipNodeRef.current && activeTooltipNodeRef.current !== linkId) {
                hideAllTooltips();
              }
              activeTooltipNodeRef.current = linkId;
              // Use the single right-docked tooltip for relationships as well
              if (tooltipRef.current) {
                tooltipRef.current.style.zIndex = 12;
                tooltipRef.current.style.display = 'block';
                tooltipRef.current.style.pointerEvents = 'auto';
                tooltipRef.current.style.opacity = 0.9;
              }
              // Get relationship type from your query
              const relationshipType = getRelationshipDisplayName(d);

              // Get properties - handle both nested and flat structure
              const props = d.properties && typeof d.properties === 'object' && !Array.isArray(d.properties)
                ? d.properties
                : d;

              // HEADER: Show the relationship type with close button
              let tooltipContent = `
                <div style="position:relative; background: linear-gradient(135deg, #ff6b6b 0%, #feca57 100%); color: white; padding: 8px 12px; margin: -8px -8px 8px -8px; font-weight: bold; border-radius: 4px 4px 0 0;">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <i class="fas fa-link" style="font-size: 16px;"></i>
                    <span>${relationshipType}</span>
                  </div>
                  ${tooltipCloseBtn}
                </div>
              `;

              // Add relationship direction info
              const currentGraphSlice = getCurrentGraphSlice();
              const currentNodes = currentGraphSlice.nodes || [];
              const srcNode = typeof d.source === 'object' ? d.source : currentNodes.find(n => n.elementId === d.source);
              const tgtNode = typeof d.target === 'object' ? d.target : currentNodes.find(n => n.elementId === d.target);
              const srcLabel = resolveNodeName(srcNode);
              const srcType = resolveNodeType(srcNode);
              const tgtLabel = resolveNodeName(tgtNode);
              const tgtType = resolveNodeType(tgtNode);

              tooltipContent += `<div style="margin: 8px; padding: 10px 12px; background: #f8f9fa; border-radius: 6px; font-size: 11px; color: #495057; border: 1px solid #e9eef5;">
                <div style="margin-bottom: 6px;"><strong style="color: #355C7D;">From:</strong> [${escapeHtml(srcType)}] ${escapeHtml(srcLabel)}</div>
                <div><strong style="color: #486581;">To:</strong> [${escapeHtml(tgtType)}] ${escapeHtml(tgtLabel)}</div>
              </div>`;

              // Show all enumerable own properties (exclude only functions)
              const allProps = Object.keys(props)
                .filter(k => typeof props[k] !== 'function')
                .map(k => [k, props[k]]);

              // Show ALL relationship properties from your query
              if (allProps.length > 0) {
                tooltipContent += `<div style="margin-top: 8px; padding: 8px; font-size: 12px; max-height: 250px; overflow-y: auto;">`;
                allProps.forEach(([k, v]) => {
                  // Format property key
                  const formattedKey = escapeHtml(k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()));

                  // Format value
                  let formattedValue = v;
                  if (v === null || v === undefined) {
                    formattedValue = '<em style="color: #95a5a6;">N/A</em>';
                  } else if (typeof v === 'object') {
                    formattedValue = escapeHtml(JSON.stringify(v));
                  } else if (typeof v === 'boolean') {
                    formattedValue = v ? '<span style="color: #27ae60;">' + CHAR_CHECK + ' Yes</span>' : '<span style="color: #e74c3c;">' + CHAR_CROSS + ' No</span>';
                  } else {
                    formattedValue = escapeHtml(String(v));
                  }

                  tooltipContent += `<div style="margin: 4px 0; padding: 3px 0; border-bottom: 1px solid #f0f0f0;"><strong style="color: #2c3e50;">${formattedKey}:</strong> <span style="color: #34495e; margin-left: 8px;">${formattedValue}</span></div>`;
                });
                tooltipContent += `</div>`;
              } else {
                tooltipContent += `<div style="margin-top: 8px; padding: 12px; font-size: 12px; color: #95a5a6; font-style: italic; text-align: center;">No properties available</div>`;
              }

              // Dock tooltip on the right side of the canvas
              if (tooltipRef.current) {
              repositionTooltip();
                  tooltipRef.current.innerHTML = tooltipContent;
                  try { applyTooltipCloseHandler(tooltipRef.current); } catch (e) { /* ignore */ }
                  try { wireTooltipRecButtons(tooltipRef.current, openTooltipRecommendation); } catch (e) { /* ignore */ }
              }
            })


          return group;
        },
        update => update,
        exit => exit.remove()
      );

    const shouldShowRelationshipLabels = simulationLinks.length <= 180;
    const linkLabel = shouldShowRelationshipLabels
      ? gRef.current.selectAll('.link-label')
        .data(simulationLinks.filter((d) => d?.type), (d) => d.elementId)
        .join(
          (enter) => enter.append('text')
            .attr('class', 'link-label')
            .attr('font-size', 9)
            .attr('font-weight', 600)
            .attr('text-anchor', 'middle')
            .attr('fill', '#516070')
            .attr('paint-order', 'stroke fill')
            .attr('stroke', '#ffffff')
            .attr('stroke-width', 3)
            .attr('stroke-linejoin', 'round')
            .style('pointer-events', 'none')
            .text((d) => getRelationshipDisplayName(d)),
          (update) => update.text((d) => getRelationshipDisplayName(d)),
          (exit) => exit.remove()
        )
      : gRef.current.selectAll('.link-label').remove();

    // const linkLabel = gRef.current
    //   .selectAll('text')
    //   .data(filteredData.links, d => d.elementId)
    //   .join('text')
    //   .text(d => d.type)
    //   .attr('font-size', 10)
    //   .attr('text-anchor', 'middle')
    //   .attr('fill', '#666')
    //   .style('pointer-events', 'none');

    // Nodes (groups containing icon and text) -- ONLY CHANGE: Using icons instead of circles
    const node = gRef.current.selectAll('.node-group')
      .data(renderData.nodes, d => d.elementId)
      .join(
        enter => {
          const group = enter.append('g')
            .attr('class', 'node-group')
            .call(d3.drag()
              .on('start', dragstarted)
              .on('drag', dragged)
              .on('end', dragended)
            );

          // Use simple colored circles (generic approach - no icons needed)
          group.append('circle')
            .attr('class', 'node-circle')
            .attr('r', NODE_RADIUS)
            .attr('fill', d => getNodeColor(d));

          // Active search node halo so the main context is obvious in the graph
          group.append('circle')
            .attr('class', 'search-active-ring')
            .attr('r', NODE_RADIUS + 8)
            .attr('fill', 'none')
            .attr('stroke', TCS_GRAPH_THEME.primary)
            .attr('stroke-width', 2.2)
            .attr('stroke-dasharray', '5,4')
            .style('pointer-events', 'none')
            .style('opacity', d => d.elementId === activeSearchResultId ? 1 : 0);

          group.append('circle')
            .attr('class', 'search-match-ring')
            .attr('r', NODE_RADIUS + 4)
            .attr('fill', 'none')
            .attr('stroke', '#2BB3C0')
            .attr('stroke-width', 1.8)
            .style('pointer-events', 'none')
            .style('opacity', d => highlightedNodeIdsRef.current.has(d.elementId) ? 1 : 0);

          // Highlight glow ring for "View in Graph" from Recommendations
          group.append('circle')
            .attr('class', 'rec-highlight-ring')
            .attr('r', NODE_RADIUS + 6)
            .attr('fill', 'none')
            .attr('stroke', '#FFD700')
            .attr('stroke-width', 1.4)
            .attr('stroke-dasharray', '4,3')
            .style('opacity', d => {
              const nm = (d.name || d.properties?.name || '').toLowerCase();
              return highlightedNodeNames.has(nm) ? 1 : 0;
            })
            .style('pointer-events', 'none')
            .each(function(d) {
              const nm = (d.name || d.properties?.name || '').toLowerCase();
              if (highlightedNodeNames.has(nm)) {
                d3.select(this)
                  .attr('stroke', '#FFD700')
                  .transition().duration(600).ease(d3.easeSinInOut)
                  .attr('r', NODE_RADIUS + 10)
                  .attr('stroke-opacity', 0.3)
                  .transition().duration(600).ease(d3.easeSinInOut)
                  .attr('r', NODE_RADIUS + 6)
                  .attr('stroke-opacity', 1)
                  .on('end', function repeat() {
                    d3.select(this)
                      .transition().duration(600).ease(d3.easeSinInOut)
                      .attr('r', NODE_RADIUS + 10)
                      .attr('stroke-opacity', 0.3)
                      .transition().duration(600).ease(d3.easeSinInOut)
                      .attr('r', NODE_RADIUS + 6)
                      .attr('stroke-opacity', 1)
                      .on('end', repeat);
                  });
              }
            });

          // Node label text (using unified logic)
          group.append('text')
            .attr('class', 'node-label')
            .text(d => showNodeLabels ? getPrimaryNodeLabel(d) : '')
            .attr('font-size', 10)
            .attr('font-weight', 'bold')
            .attr('dx', NODE_RADIUS + 5)
            .attr('dy', 3)
            .attr('fill', '#000')
            .style('display', showNodeLabels ? null : 'none')
            .style('pointer-events', 'none');

          // Expand/Collapse control circle (only for search results)
          group.append('circle')
            .attr('class', 'expand-control-bg')
            .attr('r', EXPAND_CIRCLE_RADIUS)
            .attr('cx', NODE_RADIUS + 16)
            .attr('cy', -NODE_RADIUS - 1)
            .attr('fill', d => {
              if (canCollapseNode(d)) return '#ff4444'; // Red for collapse
              if (hasExpandableConnections(d)) return '#4CAF50'; // Green for expand
              return 'transparent'; // No symbol for nodes without expandable connections
            })
            .attr('stroke', '#fff')
            .attr('stroke-width', 1)
            .style('cursor', d => {
              return (hasExpandableConnections(d) || canCollapseNode(d)) ? 'pointer' : 'default';
            })
            .style('opacity', d => {
              return (hasExpandableConnections(d) || canCollapseNode(d)) ? 1 : 0;
            })
            .on('click', (event, d) => {
              event.stopPropagation();
              logger.render('=== EXPAND/COLLAPSE BUTTON CLICKED ===');
              logger.render('Node ID:', d.elementId);
              logger.render('Can expand:', hasExpandableConnections(d));
              logger.render('Can collapse:', canCollapseNode(d));
              logger.render('Is expanded:', expandedNodesRef.current.has(d.elementId));
              logger.render('Loading nodes:', Array.from(loadingNodes));
              logger.render('Current expandedNodes state:', Array.from(expandedNodesRef.current));
              logger.render('Current nodeExpansions state:', Array.from(nodeExpansionsRef.current.keys()));

              // Direct check and call to avoid any dependency issues
              if (expandedNodesRef.current.has(d.elementId)) {
                logger.render('Node is expanded - calling collapseNode directly...');
                collapseNode(d.elementId);
              } else if (!expandedNodesRef.current.has(d.elementId) && hasExpandableConnections(d)) {
                logger.render('Node can be expanded - calling expandNode directly...');
                expandNode(d.elementId);
              } else {
                logger.render('No action taken - node cannot be expanded or collapsed');
              }
            });

          group.append('circle')
            .attr('class', 'expand-control-hitbox')
            .attr('r', EXPAND_CIRCLE_RADIUS + 6)
            .attr('cx', NODE_RADIUS + 16)
            .attr('cy', -NODE_RADIUS - 1)
            .attr('fill', 'transparent')
            .style('cursor', d => (
              (hasExpandableConnections(d) || canCollapseNode(d)) ? 'pointer' : 'default'
            ))
            .style('pointer-events', d => (
              (hasExpandableConnections(d) || canCollapseNode(d)) ? 'all' : 'none'
            ))
            .on('click', (event, d) => {
              event.stopPropagation();
              if (expandedNodesRef.current.has(d.elementId)) {
                collapseNode(d.elementId);
              } else if (hasExpandableConnections(d)) {
                expandNode(d.elementId);
              }
            });

          // Plus/Minus symbol
          group.append('text')
            .attr('class', 'expand-symbol')
            .attr('x', NODE_RADIUS + 16)
            .attr('y', -NODE_RADIUS + 1)
            .attr('text-anchor', 'middle')
            .attr('font-size', EXPAND_SYMBOL_SIZE)
            .attr('font-weight', 'bold')
            .attr('fill', '#fff')
            .style('pointer-events', 'none')
            .style('user-select', 'none')
            .text(d => {
              if (canCollapseNode(d)) return CHAR_MINUS; // Minus for collapse
              if (hasExpandableConnections(d)) return '+'; // Plus for expand
              return ''; // No symbol
            });

          // Loading indicator
          group.append('circle')
            .attr('class', 'loading-indicator')
            .attr('r', NODE_RADIUS + 5)
            .attr('fill', 'none')
            .attr('stroke', '#6C757D')
            .attr('stroke-width', 1.2)
            .attr('stroke-dasharray', '5,5')
            .style('opacity', d => loadingNodes.has(d.elementId) ? 1 : 0)
            .style('pointer-events', 'none');

          // Main node interactions - Updated to handle both icon and fallback circle
          group.on('click', function (event, d) {
            event.stopPropagation();
            // If clicking a different node, hide old tooltip first
            const nodeId = d.elementId || d.id;
            if (activeTooltipNodeRef.current && activeTooltipNodeRef.current !== nodeId) {
              hideAllTooltips();
            }
            activeTooltipNodeRef.current = nodeId;

            d3.select(this).select('.node-circle')
              .attr('stroke', 'black')
              .attr('stroke-width', 1.2);
            if (tooltipRef.current) {
              d3.select(tooltipRef.current).style('z-index', 12).style('display', 'block').style('pointer-events', 'auto');
              d3.select(tooltipRef.current).style('opacity', 0.9);
            }

            // Get properties - handle both nested and flat structure
            const props = d.properties && typeof d.properties === 'object' && !Array.isArray(d.properties)
              ? d.properties
              : d;

            // Get node type from labels (first label) - for HEADER
            const nodeType =
              d.entity_type ||
              props.entity_type ||
              ((d.labels && d.labels.length > 0) ? d.labels[0] : 'Node');

            // HEADER: Show the node label/type with close button
            let tooltipContent = buildTooltipHeader(nodeType, tooltipCloseBtn);
            // Recommendation action buttons (top, right after header)
            tooltipContent += buildRecActionBar(d);

            // Only exclude D3/graph-library internals — ALL real Neo4j properties will be shown
            const excludedProps = [
              'x', 'y', 'vx', 'vy', 'fx', 'fy', 'index',              // D3 force layout
              'depth', 'parent', 'data', 'height', 'level', 'children', // D3 tree layout
              'elementId', 'elementID', 'identity', 'labels', 'properties', '__typename', // driver metadata
            ];

            // Get all enumerable own properties (not inherited methods)
            const allProps = Object.keys(props)
              .filter(k => {
                if (excludedProps.includes(k)) return false;
                if (typeof props[k] === 'function') return false;
                return true;
              })
              .map(k => [k, props[k]]);

            // Show ALL properties from your query
            if (allProps.length > 0) {
              tooltipContent += `<div style="margin-top: 8px; padding: 8px; font-size: 12px; max-height: 200px; overflow-y: auto;">`;
              allProps.forEach(([k, v]) => {
                const formattedKey = escapeHtml(k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()));
                let formattedValue = v;
                if (v === null || v === undefined) {
                  formattedValue = '<em style="color: #95a5a6;">N/A</em>';
                } else if (typeof v === 'object') {
                  formattedValue = escapeHtml(JSON.stringify(v));
                } else if (typeof v === 'boolean') {
                  formattedValue = v ? '<span style="color: #27ae60;">' + CHAR_CHECK + ' Yes</span>' : '<span style="color: #e74c3c;">' + CHAR_CROSS + ' No</span>';
                } else {
                  formattedValue = escapeHtml(String(v));
                }
                tooltipContent += `<div style="margin: 4px 0; padding: 3px 0; border-bottom: 1px solid #f0f0f0;"><strong style="color: #2c3e50;">${formattedKey}:</strong> <span style="color: #34495e; margin-left: 8px;">${formattedValue}</span></div>`;
              });
              tooltipContent += `</div>`;
            } else {
              tooltipContent += `<div style="margin-top: 8px; padding: 12px; font-size: 12px; color: #95a5a6; font-style: italic; text-align: center;">No properties available</div>`;
            }

            // Get all connected links for use in multiple sections below
            const currentGraphSlice = getCurrentGraphSlice();
            const currentNodes = currentGraphSlice.nodes || [];
            const connectedLinks = (currentGraphSlice.links || []).filter(link =>
              getLinkEndpointId(link.source) === d.elementId || getLinkEndpointId(link.target) === d.elementId
            );

            // SECTION: Ontology Metadata (for OntologyClass nodes)
            if (nodeType === 'OntologyClass') {
              tooltipContent += `<div style="margin-top: 12px; padding-top: 12px; border-top: 2px solid #e0e0e0;">
                <div style="font-weight: bold; color: #0066B3; margin-bottom: 8px; font-size: 12px;">
                  <i class="fas fa-cube" style="margin-right: 4px;"></i>Ontology Metadata
                </div>`;

              // Show concept type
              if (props.concept_type) {
                tooltipContent += `<div style="margin: 4px 0; font-size: 11px; color: #555;">
                  <strong>Type:</strong> <span style="color: #e74c3c;">${escapeHtml(props.concept_type)}</span>
                </div>`;
              }

              // Show namespace
              if (props.namespace) {
                tooltipContent += `<div style="margin: 4px 0; font-size: 11px; color: #555; word-break: break-word;">
                  <strong>Namespace:</strong> <code style="background: #f5f5f5; padding: 2px 4px; border-radius: 2px; font-size: 10px;">${escapeHtml(props.namespace)}</code>
                </div>`;
              }

              // Show ontology ID and prefix
              if (props.ontology_id || props.prefix) {
                tooltipContent += `<div style="margin: 4px 0; font-size: 11px; color: #555;">
                  <strong>Ontology:</strong> <span style="color: #28A745;">[${escapeHtml(props.prefix || 'unknown')}]</span>
                </div>`;
              }

              tooltipContent += `</div>`;
            }

            const subclassParents = connectedLinks.filter(link => link.type === 'SUBCLASS_OF' && getLinkEndpointId(link.source) === d.elementId);
            const subclassChildren = connectedLinks.filter(link => link.type === 'SUBCLASS_OF' && getLinkEndpointId(link.target) === d.elementId);
            const domainLinks = connectedLinks.filter(link => link.type === 'DOMAIN' && getLinkEndpointId(link.source) === d.elementId);
            const rangeLinks = connectedLinks.filter(link => link.type === 'RANGE' && getLinkEndpointId(link.source) === d.elementId);

            if (subclassParents.length > 0 || subclassChildren.length > 0 || domainLinks.length > 0 || rangeLinks.length > 0) {
              tooltipContent += `<div style="margin-top: 12px; padding-top: 12px; border-top: 2px solid #e0e0e0;">
                <div style="font-weight: bold; color: #355C7D; margin-bottom: 8px; font-size: 12px;">
                  <i class="fas fa-project-diagram" style="margin-right: 4px;"></i>Ontology Semantics
                </div>`;

              const renderSemanticList = (title, links, direction) => {
                if (links.length === 0) return '';
              const rows = links.slice(0, 8).map((link) => {
                  const targetId = direction === 'outgoing' ? getLinkEndpointId(link.target) : getLinkEndpointId(link.source);
                  const targetNode = currentNodes.find(n => n.elementId === targetId);
                  return `<div style="margin: 4px 0; padding: 5px 8px; background: #f8fafc; border: 1px solid #e6edf5; border-radius: 5px; font-size: 11px; color: #334e68;">
                    [${escapeHtml(resolveNodeType(targetNode))}] ${escapeHtml(resolveNodeName(targetNode))}
                  </div>`;
                }).join('');
                return `<div style="margin-top: 8px;">
                  <div style="font-size: 11px; font-weight: 700; color: #52606D; margin-bottom: 4px;">${title}</div>
                  ${rows}
                </div>`;
              };

              tooltipContent += renderSemanticList('Parent Classes', subclassParents, 'outgoing');
              tooltipContent += renderSemanticList('Child Classes', subclassChildren, 'incoming');
              tooltipContent += renderSemanticList('Domain Targets', domainLinks, 'outgoing');
              tooltipContent += renderSemanticList('Range Targets', rangeLinks, 'outgoing');
              tooltipContent += `</div>`;
            }

            // SECTION: Data Properties (OntologyProperty nodes with PROPERTY_OF relationship)
            const dataProperties = connectedLinks.filter(link =>
              (link.type === 'PROPERTY_OF' && getLinkEndpointId(link.source) === d.elementId) ||
              (link.type === 'PROPERTY_OF' && getLinkEndpointId(link.target) === d.elementId)
            );

            if (dataProperties.length > 0) {
              tooltipContent += `<div style="margin-top: 12px; padding-top: 12px; border-top: 2px solid #e0e0e0;">
                <div style="font-weight: bold; color: #28A745; margin-bottom: 8px; font-size: 12px;">
                  <i class="fas fa-list" style="margin-right: 4px;"></i>Data Properties (${dataProperties.length})
                </div>`;

              dataProperties.forEach(link => {
                const isPropOwner = getLinkEndpointId(link.source) === d.elementId;
                const propNodeId = isPropOwner ? getLinkEndpointId(link.target) : getLinkEndpointId(link.source);
                const propNode = currentNodes.find(n => n.elementId === propNodeId);
                const propName = propNode?.name || 'Unknown';

                tooltipContent += `<div style="margin: 4px 0; padding: 4px; background: #f0f8f0; border-left: 3px solid #28A745; font-size: 11px;">
                  <strong style="color: #28A745;">⚙</strong> ${escapeHtml(propName)}
                </div>`;
              });

              tooltipContent += `</div>`;
            }

            // SECTION: Other Relationships (non-PROPERTY_OF)
            const otherRelationships = connectedLinks.filter(link => link.type !== 'PROPERTY_OF');

            if (otherRelationships.length > 0) {
              tooltipContent += `<div style="margin-top: 12px; padding-top: 12px; border-top: 2px solid #e0e0e0;">
                <div style="font-weight: bold; color: #0066B3; margin-bottom: 8px; font-size: 12px;">
                  <i class="fas fa-link" style="margin-right: 4px;"></i>Relationships (${otherRelationships.length})
                </div>`;

              otherRelationships.forEach(link => {
                const isOutgoing = getLinkEndpointId(link.source) === d.elementId;
                const otherNodeId = isOutgoing ? getLinkEndpointId(link.target) : getLinkEndpointId(link.source);
                const otherNode = currentNodes.find(n => n.elementId === otherNodeId);
                const otherNodeProps = otherNode?.properties || {};
                const otherNodeName =
                  otherNode?.entity_type ||
                  otherNodeProps.entity_type ||
                  otherNode?.name ||
                  otherNodeProps.name ||
                  otherNode?.title ||
                  otherNodeProps.title ||
                  otherNode?.label ||
                  otherNode?.labels?.[0] ||
                  'Unknown';
                const otherNodeType =
                  otherNode?.entity_type ||
                  otherNodeProps.entity_type ||
                  otherNode?.label ||
                  otherNode?.labels?.[0] ||
                  'Node';
              const relationshipType = escapeHtml(getRelationshipDisplayName(link));
                const arrow = isOutgoing ? '→' : '←';

                tooltipContent += `<div style="margin: 6px 0; padding: 6px; background: #f5f5f5; border-radius: 3px; font-size: 11px;">
                  <div style="color: #555; margin-bottom: 2px;">
                    <strong style="color: #28A745;">${arrow}</strong>
                    <strong style="color: #e74c3c;">${relationshipType}</strong>
                  </div>
                  <div style="color: #0066B3; font-weight: 500; margin-left: 16px;">
                    [${escapeHtml(otherNodeType)}] ${escapeHtml(otherNodeName)}
                  </div>
                </div>`;
              });

              tooltipContent += `</div>`;
            }

            // Dock tooltip on the right side of the canvas
            if (tooltipRef.current) {
              repositionTooltip();
              tooltipRef.current.innerHTML = tooltipContent;
              try { applyTooltipCloseHandler(tooltipRef.current); } catch (e) { /* ignore */ }
              try { wireTooltipRecButtons(tooltipRef.current, openTooltipRecommendation); } catch (e) { /* ignore */ }
            }
          })
          .on('mouseout', function () {
            d3.select(this).select('.node-circle')
              .attr('stroke', null)
              .attr('stroke-width', null);
          });

          return group;
        },
        update => {
          // Update circle color based on label
          update.select('.node-circle')
            .attr('fill', d => getNodeColor(d));

          update.select('.search-active-ring')
            .style('opacity', d => d.elementId === activeSearchResultId ? 1 : 0)
            .attr('stroke', d => d.elementId === activeSearchResultId ? TCS_GRAPH_THEME.primary : 'none');

          update.select('.search-match-ring')
            .style('opacity', d => highlightedNodeIdsRef.current.has(d.elementId) ? 1 : 0);

          update.each(function(d) {
            if (d.elementId === activeSearchResultId) {
              d3.select(this).raise();
            }
          });

          update.select('.node-label')
            .text(d => showNodeLabels ? getPrimaryNodeLabel(d) : '')
            .attr('font-weight', 'bold')
            .attr('fill', '#000')
            .style('display', showNodeLabels ? null : 'none');

          // Update expand/collapse control visibility and color
          update.select('.expand-control-bg')
            .attr('fill', d => {
              if (canCollapseNode(d)) return '#ff4444'; // Red for collapse
              if (hasExpandableConnections(d)) return '#4CAF50'; // Green for expand
              return 'transparent';
            })
            .style('opacity', d => {
              return (hasExpandableConnections(d) || canCollapseNode(d)) ? 1 : 0;
            });

          // Update symbol
          update.select('.expand-symbol')
            .text(d => {
              if (canCollapseNode(d)) return CHAR_MINUS; // Minus for collapse
              if (hasExpandableConnections(d)) return '+'; // Plus for expand
              return '';
            });

          // Update loading indicator
          update.select('.loading-indicator')
            .style('opacity', d => loadingNodes.has(d.elementId) ? 1 : 0);

          return update;
        },
        exit => exit.remove()
      );

    link
      .attr('stroke', d => getRelationshipVisual(d.type).color)
      .attr('stroke-opacity', LINK_OPACITY)
      .attr('stroke-width', d => getRelationshipVisual(d.type).width)
      .attr('stroke-dasharray', d => getRelationshipVisual(d.type).dasharray)
      .attr('marker-end', d => `url(#${getRelationshipVisual(d.type).markerId})`);

     // NODE LABELS
    //  const labels = gRef.current.selectAll('.text')
    //  .data(filteredData.nodes, d => d.elementId)
    //  .join('text')
    //  .text(d => {
    //   if(d[`${d.type}_name`]){
    //     return d[`${d.type}_name`]
    //   }else{
    //     return d.label
    //   }}
    //   )
    //  .attr('font-size', 10)
    //  .attr('dy', -15)
    //  .attr('text-anchor', 'middle')
    //  .attr('pointer-events', 'none')
    //  .attr('fill', '#333');

    renderLinkPath(link);
    renderNodePositions(node);
    if (shouldShowRelationshipLabels && linkLabel) {
      linkLabel
        .attr('x', (d) => {
          const sourceNode = resolveLinkNode(d.source);
          const targetNode = resolveLinkNode(d.target);
          const sourceX = sourceNode?.x ?? 0;
          const targetX = targetNode?.x ?? 0;
          return (sourceX + targetX) / 2;
        })
        .attr('y', (d) => {
          const sourceNode = resolveLinkNode(d.source);
          const targetNode = resolveLinkNode(d.target);
          const sourceY = sourceNode?.y ?? 0;
          const targetY = targetNode?.y ?? 0;
          return ((sourceY + targetY) / 2) - 6;
        });
    }

    simulationRef.current.on('tick', () => {
      if (tickFrameRef.current) return;
      tickFrameRef.current = requestAnimationFrame(() => {
        tickFrameRef.current = null;
        renderLinkPath(link);
        renderNodePositions(node);
        if (shouldShowRelationshipLabels && linkLabel) {
          linkLabel
            .attr('x', (d) => {
              const sourceNode = resolveLinkNode(d.source);
              const targetNode = resolveLinkNode(d.target);
              const sourceX = sourceNode?.x ?? 0;
              const targetX = targetNode?.x ?? 0;
              return (sourceX + targetX) / 2;
            })
            .attr('y', (d) => {
              const sourceNode = resolveLinkNode(d.source);
              const targetNode = resolveLinkNode(d.target);
              const sourceY = sourceNode?.y ?? 0;
              const targetY = targetNode?.y ?? 0;
              return ((sourceY + targetY) / 2) - 6;
            });
        }
      });
    });

    // Center the view on search results, prioritizing the active exact match
    if (graphSearchActive && activeDisplayData.nodes.length > 0 && lastCenteredSearchRef.current !== debouncedSearchQuery) {
      const focusNode = activeDisplayData.nodes.find((d) => d.elementId === activeSearchResultId) || activeDisplayData.nodes[0];
      const hasFocusCoords = Number.isFinite(focusNode?.x) && Number.isFinite(focusNode?.y);

      let centerX = width / 2;
      let centerY = height / 2;
      if (hasFocusCoords) {
        centerX = focusNode.x;
        centerY = focusNode.y;
      } else {
        const nodePositions = filteredData.nodes.map(d => ({ x: d.x || 0, y: d.y || 0 }));
        const minX = Math.min(...nodePositions.map(d => d.x));
        const maxX = Math.max(...nodePositions.map(d => d.x));
        const minY = Math.min(...nodePositions.map(d => d.y));
        const maxY = Math.max(...nodePositions.map(d => d.y));
        centerX = (minX + maxX) / 2;
        centerY = (minY + maxY) / 2;
      }

      const transform = d3.zoomIdentity
        .translate(width / 2 - centerX, height / 2 - centerY)
        .scale(1);

      if (zoomBehaviorRef.current) {
        svg.call(zoomBehaviorRef.current.transform, transform);
      }
      lastCenteredSearchRef.current = debouncedSearchQuery;
    } else if (!graphSearchActive && lastCenteredSearchRef.current) {
      lastCenteredSearchRef.current = '';
      userInteractedWithGraphRef.current = false;
    }

    // Performance monitoring
    const endTime = performance.now();
    const renderTime = endTime - startTime;
    performanceLog(`[PERF] Render completed in ${renderTime.toFixed(2)}ms`);

    // Performance warnings
    if (renderTime > 1000) {
      performanceWarn(`[WARN] Slow render detected: ${renderTime.toFixed(2)}ms with ${filteredData.nodes?.length || 0} nodes`);
    }
    if (renderTime > 2000) {
      performanceWarn(`[ALERT] Very slow render: ${renderTime.toFixed(2)}ms - consider optimization`);
    }

    return () => {
      if (tickFrameRef.current) {
        cancelAnimationFrame(tickFrameRef.current);
        tickFrameRef.current = null;
      }
      if (simulationRef.current) {
        // Keep the simulation instance alive across ordinary React effect reruns.
        // Fully stopping and nulling it here forces unnecessary reinitialization
        // and contributes to layout instability.
        simulationRef.current.on('tick', null);
      }
      // Clear any remaining event listeners
      if (gRef.current) {
        gRef.current.selectAll('*').on('.drag', null);
      }
      d3.select(svgElement).on('.zoom', null);
    };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDisplayData, activeGraphDataset, searchResultData, filteredData, graphSearchActive, graphViewMode, selectedOntology, layoutType, treeExpandedNodes, handleZoom]);

  // Separate effect: apply/remove "View in Graph" highlights via direct D3 DOM manipulation
  // This avoids re-rendering the entire graph just to toggle highlights
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    const hasHighlights = highlightedNodeNames.size > 0;

    // Force-directed layout: add/remove glow rings on .node-group circles
    svg.selectAll('.node-group').each(function(d) {
      const group = d3.select(this);
      const nm = (d?.name || d?.properties?.name || '').toLowerCase();
      const isHighlighted = hasHighlights && highlightedNodeNames.has(nm);

      // Remove any existing highlight ring
      group.selectAll('.view-in-graph-ring').remove();

      if (isHighlighted) {
        // Add pulsing gold ring
        const ring = group.insert('circle', ':first-child')
          .attr('class', 'view-in-graph-ring')
          .attr('r', 18)
          .attr('fill', 'none')
          .attr('stroke', '#FFD700')
          .attr('stroke-width', 1.4)
          .attr('stroke-dasharray', '4,3')
          .style('pointer-events', 'none');
        // Pulse animation
        (function pulse() {
          ring.transition().duration(600).ease(d3.easeSinInOut)
            .attr('r', 22).attr('stroke-opacity', 0.3)
            .transition().duration(600).ease(d3.easeSinInOut)
            .attr('r', 18).attr('stroke-opacity', 1)
            .on('end', pulse);
        })();
      }
    });

    // Tree layout: highlight row backgrounds
    svg.selectAll('.tree-row').each(function(d) {
      const row = d3.select(this);
      const nm = (d?.name || d?.properties?.name || '').toLowerCase();
      const isHighlighted = hasHighlights && highlightedNodeNames.has(nm);
      const rect = row.select('rect');
      if (isHighlighted) {
        rect.attr('fill', '#FFF9C4').attr('stroke', '#FFD700').attr('stroke-width', 1.25);
      }
    });
  }, [highlightedNodeNames]);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('.node-group').each(function(d) {
      const group = d3.select(this);
      const isHighlighted = highlightedNodeIds.has(d?.elementId);
      group.select('.search-match-ring')
        .style('opacity', isHighlighted ? 1 : 0)
        .attr('stroke', isHighlighted ? '#2BB3C0' : 'none');
      group.select('.node-label')
        .attr('fill', isHighlighted ? TCS_GRAPH_THEME.primary : '#000');
    });
  }, [highlightedNodeIds]);

  // Keyboard shortcuts for expand/collapse
  useEffect(() => {
    const handleKeyPress = (event) => {
      if (event.key === 'Escape') {
        // Collapse all nodes and reset to original search results
        resetGraphSelectionState({ resetOntology: false, resetStepPart: false, resetSearch: false });
        setFilteredData(graphData);
        setFullDataset(graphData);
        setData(graphData);
        if (!searchModeRef.current) syncSharedSearchResults(graphData.nodes);
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, resetGraphSelectionState]);

  // Preserve expand/collapse state while search text changes; only reset when
  // the search is explicitly cleared so the canvas does not jump on small edits.
  useEffect(() => {
    const previousSearchQuery = previousSearchQueryRef.current;
    if (previousSearchQuery && !searchQuery) {
      resetGraphSelectionState({ resetOntology: false, resetStepPart: false, resetSearch: false });
    }
    previousSearchQueryRef.current = searchQuery;
  }, [searchQuery, resetGraphSelectionState]);

  // [OK] CLEANUP: Final cleanup on component unmount
  useEffect(() => {
    const timeouts = timeoutsRef.current;
    return () => {
      // Clear all pending timeouts
      if (timeouts) {
        timeouts.forEach(id => clearTimeout(id));
        timeouts.clear();
      }
      // Stop D3 simulation if running
      if (simulationRef.current) {
        simulationRef.current.stop();
        simulationRef.current = null;
      }
    };
  }, []);

  return (
    <div
      className="graph-heb-root"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        background: `linear-gradient(180deg, ${TCS_GRAPH_THEME.surfaceMuted} 0%, #F2F5F8 100%)`,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* STATIC TOOLBAR (prevents overlap with graph + tree layouts) */}
      <GraphExplorerToolbar
        theme={TCS_GRAPH_THEME}
        graphViewMode={graphViewMode}
        selectedOntology={selectedOntology}
        searchInput={searchInput}
        onSearchInputChange={(value) => {
          const nextValue = typeof value === 'string' ? value : '';
          setSearchInput(nextValue);
          if (!normalizeSearchTerm(nextValue)) {
            contextualSearchRequestIdRef.current += 1;
            setSearchQuery('');
          }
        }}
        onSearchSubmit={submitSearchQuery}
        searchLoading={searchLoading}
        searchResultMode={searchResultMode}
        onSearchResultModeChange={(mode) => {
          setSearchResultMode(mode);
          if (debouncedSearchQueryRef.current) {
            lastCenteredSearchRef.current = '';
          }
        }}
        onToolTargetSelect={(target) => {
          if (typeof setActiveTab === 'function') setActiveTab(target);
        }}
        onOpenFullGraph={() => {
          if (selectedOntology && selectedOntology !== 'ALL') {
            lastSpecificOntologyRef.current = selectedOntology;
          }
          setGraphViewMode('ontology');
          graphViewModeRef.current = 'ontology';
          setSelectedOntology('ALL');
          selectedOntologyRef.current = 'ALL';
          resetGraphSelectionState({ resetOntology: false, resetStepPart: true, dataOverride: initialData });
          commitGraphSlice(initialData, {
            updateGraphData: true,
            updateFullDataset: true,
            updateSearchResultData: true,
            syncResults: !searchModeRef.current,
          });
        }}
        onOpenOntologyGraph={() => {
          const nextOntology = lastSpecificOntologyRef.current !== 'ALL'
            ? lastSpecificOntologyRef.current
            : preferredOntologyValue;
          setGraphViewMode('ontology');
          graphViewModeRef.current = 'ontology';
          if (nextOntology === 'ALL') {
            setOntologyGraphMessage('No registered ontology graph is available yet.');
          }
          if (nextOntology !== 'ALL') {
            setSelectedOntology(nextOntology);
            selectedOntologyRef.current = nextOntology;
          }
        }}
        onOpenContextualGraph={() => {
          setGraphViewMode('individual');
          graphViewModeRef.current = 'individual';
          setSelectedOntology('ALL');
          selectedOntologyRef.current = 'ALL';
          const nextRootId = resolveContextualEntryNodeId(searchInput);
          if (nextRootId) {
            setTimeout(() => {
              loadContextualRootGraph(nextRootId, { preserveSearch: true });
            }, 0);
            return;
          }
          if (searchInput?.trim()) {
            setSearchQuery(normalizeSearchTerm(searchInput));
          }
        }}
        ontologyLoading={ontologyLoading}
        ontologyError={ontologyError}
        ontologyOptions={ontologyOptions}
        onSelectedOntologyChange={setSelectedOntology}
        selectedStepPart={selectedStepPart}
        stepPartsLoading={stepPartsLoading}
        stepPartsError={stepPartsError}
        stepParts={stepParts}
        onSelectedStepPartChange={(part) => {
          setSelectedStepPart(part);
          if (part === 'ALL' && selectedOntologyRef.current === 'step') {
            fetchOntologyGraph('step', 'ALL');
          }
        }}
        isLayoutSwitching={isLayoutSwitching}
        ontologyGraphMessage={ontologyGraphMessage}
        ontologySliceSummary={ontologySliceSummary}
        getRelationshipVisual={getRelationshipVisual}
        graphSearchActive={graphSearchActive}
        onReset={() => {
          setGraphViewMode('ontology');
          graphViewModeRef.current = 'ontology';
          resetGraphSelectionState({ dataOverride: initialData });
          commitGraphSlice(initialData, {
            updateGraphData: true,
            updateFullDataset: true,
            updateSearchResultData: true,
            syncResults: !searchModeRef.current,
          });
        }}
        showChat={showChat}
        onToggleChat={toggleChat}
      />
      {isLoading && (
        <div className="loading-state" style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 11,
          background: 'rgba(255,255,255,0.98)',
          padding: '32px 40px',
          borderRadius: '16px',
          textAlign: 'center',
          boxShadow: '0 12px 40px rgba(0,0,0,0.15)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(0,0,0,0.1)',
          minWidth: '280px'
        }}>
          <div style={{ marginBottom: '12px', fontSize: '13px', fontWeight: 700, color: '#52606d' }}>Loading graph</div>
          <div style={{ fontSize: '18px', fontWeight: '600', color: '#2C2C2C', marginBottom: '8px' }}>Loading Graph Data</div>
          <div style={{ fontSize: '14px', color: '#7f8c8d' }}>Please wait while we fetch your data...</div>
        </div>
      )}
      {error && (
        <div className="error-state" style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 11,
          background: 'rgba(255,255,255,0.98)',
          padding: '32px 40px',
          borderRadius: '16px',
          textAlign: 'center',
          boxShadow: '0 12px 40px rgba(231, 76, 60, 0.15)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(231, 76, 60, 0.2)',
          minWidth: '320px'
        }}>
          <div style={{ marginBottom: '16px', fontSize: '48px', color: '#28A745' }}><i className="fas fa-exclamation-triangle"></i></div>
          <div style={{ fontSize: '18px', fontWeight: '600', color: '#28A745', marginBottom: '8px' }}>Connection Error</div>
          <div style={{ fontSize: '14px', color: '#7f8c8d' }}>{error}</div>
        </div>
      )}
      {!isLoading && !error && graphViewMode !== 'individual' && graphSearchActive && !searchLoading && debouncedSearchQuery && searchResultData.nodes.length === 0 && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 11,
          background: 'rgba(255,255,255,0.98)',
          padding: '32px 40px',
          borderRadius: '16px',
          textAlign: 'center',
          boxShadow: '0 12px 40px rgba(0,0,0,0.1)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(0,0,0,0.1)',
          minWidth: '320px'
        }}>
          <div style={{ marginBottom: '16px', fontSize: '48px', color: '#6c757d' }}><i className="fas fa-search"></i></div>
          <div style={{ fontSize: '18px', fontWeight: '600', color: '#2C2C2C', marginBottom: '8px' }}>No Results Found</div>
          <div style={{ fontSize: '14px', color: '#7f8c8d', marginBottom: '4px' }}>No nodes found for: <strong>"{debouncedSearchQuery}"</strong></div>
          <div style={{ fontSize: '12px', color: '#95a5a6' }}>Try adjusting your search terms</div>
        </div>
      )}
      {!isLoading && !error && graphViewMode !== 'individual' && graphData.nodes.length === 0 && !searchQuery && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 11,
          background: 'rgba(255,255,255,0.98)',
          padding: '32px 40px',
          borderRadius: '16px',
          textAlign: 'center',
          boxShadow: '0 12px 40px rgba(0,0,0,0.1)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(0,0,0,0.1)',
          minWidth: '320px'
        }}>
          <div style={{ marginBottom: '16px', fontSize: '48px', color: '#6c757d' }}><i className="fas fa-chart-line"></i></div>
          <div style={{ fontSize: '18px', fontWeight: '600', color: '#2C2C2C', marginBottom: '8px' }}>No Data Available</div>
          <div style={{ fontSize: '14px', color: '#7f8c8d' }}>No graph data available from Neo4j database</div>
        </div>
      )}
      {!isLoading && !error && graphViewMode === 'individual' && !searchLoading && activeGraphDataset.nodes.length === 0 && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 11,
          background: 'rgba(255,255,255,0.98)',
          padding: '28px 34px',
          borderRadius: '16px',
          textAlign: 'center',
          boxShadow: '0 12px 40px rgba(0,0,0,0.1)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(0,0,0,0.08)',
          minWidth: '320px'
        }}>
          <div style={{ marginBottom: '12px', fontSize: '18px', fontWeight: 700, color: '#2C2C2C' }}>Contextual Instance Graph</div>
          <div style={{ fontSize: '13px', color: '#7f8c8d', marginBottom: '4px' }}>Search for an instance to load its one-hop connected graph.</div>
          <div style={{ fontSize: '12px', color: '#95a5a6' }}>Matched nodes open as the root and can be expanded one hop at a time.</div>
        </div>
      )}

  <svg ref={svgRef} style={{ width: '100%', flex: '1 1 auto', minHeight: 0, margin: 0, padding: 0, position: 'relative', zIndex: 0 }}></svg>

      <div ref={tooltipRef} className="tooltip" style={{
        position: 'absolute',
        opacity: 0,
        background: TCS_GRAPH_THEME.surface,
        color: TCS_GRAPH_THEME.ink,
        padding: '10px 12px',
        borderRadius: '10px',
        pointerEvents: 'none',
        maxWidth: '360px',
        minWidth: '320px',
        maxHeight: '80vh',
        overflowY: 'auto',
        fontSize: '12px',
        lineHeight: 1.45,
        border: `1px solid ${TCS_GRAPH_THEME.border}`,
        boxShadow: '0 18px 40px rgba(15, 23, 42, 0.18)',
        zIndex: 12,
        display: 'none'
      }} />

      {/* Recommendation Slide-in Panel */}
      {recPanel.open && (
        <div style={{
          position: 'absolute', top: 0, right: 0, width: '380px', height: '100%',
          background: '#fff', boxShadow: '-4px 0 16px rgba(0,0,0,0.12)',
          zIndex: 3000, display: 'flex', flexDirection: 'column',
          borderLeft: '2px solid #004B87', borderRadius: '0 0 0 8px',
          animation: 'slideInRight 0.25s ease-out',
        }}>
          {/* Panel header */}
          <div style={{
            padding: '12px 16px', background: 'linear-gradient(135deg, #004B87 0%, #0077B6 100%)',
            color: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <div style={{ fontWeight: 700, fontSize: '14px' }}>
              {recPanel.service === 'change-impact' ? 'Change Impact' :
               recPanel.service === 'similar-parts' ? '[FIND] Similar Parts' : '[MFG] Manufacturing'}
            </div>
            <button onClick={() => setRecPanel({ open: false, service: null, nodeName: '', loading: false, result: null, error: '' })}
              style={{ background: 'none', border: 'none', color: '#fff', fontSize: '18px', cursor: 'pointer', padding: '0 4px' }}>&times;</button>
          </div>
          {/* Panel body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px', fontSize: '13px' }}>
            <div style={{ color: '#7f8c8d', marginBottom: '10px' }}>
              Node: <strong style={{ color: '#2c3e50' }}>{recPanel.nodeName}</strong>
            </div>
            {recPanel.loading && (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#7f8c8d' }}>
                <div style={{ width: 28, height: 28, border: '3px solid #eee', borderTop: '3px solid #004B87', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 10px' }} />
                Analysing...
              </div>
            )}
            {recPanel.error && <div style={{ color: '#e74c3c', padding: '10px', background: '#fdf2f2', borderRadius: '6px' }}>{recPanel.error}</div>}
            {recPanel.result && <RecPanelResult service={recPanel.service} data={recPanel.result} setRecPanel={setRecPanel} setActiveTab={setActiveTab} />}
          </div>
        </div>
      )}

    </div>
  );
}

// Performance: Add CSS-in-JS for spinner animation
const spinnerStyles = document.createElement('style');
spinnerStyles.textContent = `
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;
if (!document.head.querySelector('style[data-spinner]')) {
  spinnerStyles.setAttribute('data-spinner', 'true');
  document.head.appendChild(spinnerStyles);
}

export default React.memo(GraphHEB);
