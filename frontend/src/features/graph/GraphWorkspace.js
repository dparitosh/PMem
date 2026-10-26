import OntologyGroupOverview from './OntologyGroupOverview';
import GraphInvestigation from './GraphInvestigation';
import GraphInspector from './GraphInspector';
import useGraphData from './hooks/useGraphData';
import GraphCanvas from "./GraphCanvas";
import { TCS_GRAPH_THEME, getNodeSemanticFamily, resolveNodeType, resolveNodeName, getRelationshipVisual, getVisibleRelationshipOpacity, getVisibleRelationshipStrokeWidth, escapeHtml, performanceLog, isDevelopment, performanceWarn } from "./graphRenderingPolicy";
import React, { useEffect, useRef, useState, useCallback, useMemo, startTransition } from 'react';
import * as d3 from 'd3';
import "./GraphWorkspace.css";
import { useOntologies } from "../../contexts/OntologyContext";
import { logger } from "../../utils/logger";
import { safeGet, safeString } from "../../utils/safeAccess";
import { deduplicateNodesAndLinks, isCadBusinessObjectNode, isMetadataWrapperNode, isRelationshipCarrierNode, normalizeGraphDataset as normalizeGraphDatasetShared, normalizeSearchTerm, validateConnectivity, getLinkEndpointId } from "../../utils/graphUtils";
import { buildUrl, API } from "../../config";
import { apiClient, platformAPI } from "../../services/apiClient";
import { graphApi } from "../../services/graphApi";
import { searchLoadedGraph } from "../../utils/universalGraphSearch";

import GraphFilters from "./GraphFilters";
import useMountedRef from "../../hooks/useMountedRef";
import { buildNodeHighlightTerms } from "../../utils/graphDisplayPolicy";

import { rebuildExpandedGraph, boundExpansionSlice, seedSimulationNodes } from "../../utils/graphInteractionState";

function consumePendingEvents(key) {
  if (typeof window === 'undefined' || !window[key]) return [];
  const pending = window[key];
  delete window[key];
  return Array.isArray(pending) ? pending : [pending];
}

// Security: HTML-escape utility for tooltip interpolation

//
// DISPLAY_NAME_PROPERTY  ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â priority-ordered list of node properties to try.
//   The first property found on a node is used as the display name.
//   Set to [] (empty array) to rely solely on the knowledge graph label.
const DISPLAY_NAME_PROPERTY = ['name', 'title', 'code', 'key', 'abbreviation', 'entity_type'];

// Define constants for graph tuning values.
// These improve readability and maintainability
const HIGHLIGHT_AUTO_CLEAR_MS = 15000;        // 15 seconds - clear highlight after timeout
const ENTITY_EXTRACTION_DELAY_MS = 500;       // 500ms - allow text selection to settle
const DEFAULT_GRAPH_OVERVIEW_LIMIT = Math.max(1, Number(API?.ui?.graphMaxNodes) || 750);
const DEFAULT_ONTOLOGY_VIEW_LIMIT = DEFAULT_GRAPH_OVERVIEW_LIMIT;
// Helper: resolve the first matching property from DISPLAY_NAME_PROPERTY list
const resolveDisplayProp = (props) => {
  if (!props || !DISPLAY_NAME_PROPERTY || DISPLAY_NAME_PROPERTY.length === 0) return null;
  for (const key of DISPLAY_NAME_PROPERTY) {
    const value = safeGet(props, key, null);
    if (value != null) return String(value);
  }
  return null;
};

const resolveOntologySearchPrefix = (ontologyValue, fallbackOntologyValue = '') => {
  if (!ontologyValue || ontologyValue === 'ALL' || ontologyValue === 'step' || ontologyValue === 'mbse_instances') {
    if (!fallbackOntologyValue || fallbackOntologyValue === ontologyValue) {
      return '';
    }
    return resolveOntologySearchPrefix(fallbackOntologyValue, '');
  }
  if (ontologyValue.endsWith('_instances')) {
    return ontologyValue.replace(/_instances$/, '');
  }
  return ontologyValue;
};

// Performance: Disable excessive console logging in production

// Render recommendation results in the slide-in panel.

// Define constants for D3 parameters and styling

        // TCS-inspired muted steel link

        // Balanced spread for dense contextual graphs
const ALPHA_TARGET_DRAG = 0.3;
const ALPHA_TARGET_END = 0;

// NEW CONSTANTS FOR CENTERING AND VIEWPORT

const VIEWPORT_PADDING = 50;

// NEW CONSTANTS FOR EXPAND/COLLAPSE

// NEW CONSTANTS FOR ARROWHEADS

     // ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¹ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢   minus sign
     // ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ   check mark
     // ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â   ballot x

const ENTITY_COLOR_SWATCH = [
  '#1F3D63', '#0F766E', '#7C3AED', '#C05621', '#0E7490', '#A16207',
  '#BE185D', '#486581', '#355C7D', '#2F855A', '#B45309', '#6B46C1',
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
          node?.label,
          node?.type,
          node?.entity_type,
          node?.code,
          Array.isArray(node?.labels) ? node.labels.join(' ') : null,
          props.id,
          props.uid,
          props.name,
          props.title,
          props.label,
          props.type,
          props.entity_type,
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

const varyColorBySeed = (baseColor, seed, options = {}) => {
  const {
    lightnessRange = 18,
    saturationBoost = 0,
    chromaFloor = 26,
  } = options;
  const color = d3.hcl(baseColor);
  if (!color) return baseColor;
  const hash = hashText(seed || baseColor);
  const offset = (hash % (lightnessRange * 2 + 1)) - lightnessRange;
  color.l = Math.max(32, Math.min(78, color.l + offset));
  color.c = Math.max(chromaFloor, Math.min(92, color.c + saturationBoost + ((hash % 9) - 4)));
  return color.formatHex();
};

const ONTOLOGY_CLASS_PALETTE = ['#163E6D', '#1D4F91', '#2563EB', '#3B82F6', '#5B9BFF', '#2B6CB0'];
const OBJECT_PROPERTY_PALETTE = ['#C05621', '#DD6B20', '#F97316', '#FB923C', '#EA580C', '#B45309'];
const DATATYPE_PROPERTY_PALETTE = ['#2C5282', '#3B82F6', '#60A5FA', '#D97706', '#F59E0B', '#FDBA74'];

const pickPaletteColor = (palette, seed) => {
  if (!Array.isArray(palette) || palette.length === 0) return TCS_GRAPH_THEME.primary;
  return palette[hashText(seed) % palette.length];
};

export const normalizeGraphDataset = (payload, options) => normalizeGraphDatasetShared(payload, options);

export const sanitizeContextualGraph = (graphData, rootNodeId) => {
  const neighborhood = graphData;
  const rootId = String(rootNodeId || '').trim();
  const preserveSchemaNodes = graphData?.view?.fallback === 'schema';
  const businessLabels = new Set(['part','product','productrevision','partversion','individual','namedindividual','requirement','requirementrevision','document','specification','occurrence','productinstance','process','processinstance','activity','change','changerequest','changerequestrevision','changeorder','assembly','feature','shape','datum','dimension','tolerance','geometrictolerance']);
  const nodes = (neighborhood.nodes || []).filter((node) => {
    if (!node?.elementId) return false;
    if (node.elementId === rootId) return true;
    const business = isCadBusinessObjectNode(node) || (node.labels || []).some(label=>businessLabels.has(String(label).toLowerCase())) || businessLabels.has(String(node.properties?.semantic_role || '').trim().toLowerCase());
    return business && !isMetadataWrapperNode(node)
      && (preserveSchemaNodes || !isSchemaTerminalNode(node));
  });
  const nodeIds = new Set(nodes.map((node) => node.elementId));
  const links = (neighborhood.links || []).map(link=>link.properties?.collapsed ? {...link,type:'SOURCE_PATH',properties:{...link.properties,projection:'Undirected source path through a relationship record; not an asserted direct edge'}} : link).filter((link) => {
    const sourceId = getLinkEndpointId(link.source);
    const targetId = getLinkEndpointId(link.target);
    return nodeIds.has(sourceId) && nodeIds.has(targetId);
  });
  // Retain only the root-connected component after hiding metadata wrappers.
  const adjacent = new Map(nodes.map(node=>[node.elementId, []]));
  links.forEach(link=>{const a=getLinkEndpointId(link.source), b=getLinkEndpointId(link.target);adjacent.get(a).push(b);adjacent.get(b).push(a);});
  const connected = new Set(), pending = [rootId];
  while(pending.length){const id=pending.pop();if(connected.has(id)||!adjacent.has(id))continue;connected.add(id);pending.push(...adjacent.get(id));}
  return deduplicateNodesAndLinks(nodes.filter(node=>connected.has(node.elementId)), links.filter(link=>connected.has(getLinkEndpointId(link.source))&&connected.has(getLinkEndpointId(link.target))));
};

const GraphWorkspace = ({
  setData = () => {},
  setSearchResults = () => {},
  showChat,
  toggleChat,
  setActiveTab = () => {},
  setVisibleRelationships = () => {},
  chatResults,
}) => {
  const svgRef = useRef();
  const tooltipRef = useRef();

  const simulationRef = useRef(null);
  const gRef = useRef(null); // Ref for the main D3 group element
  const zoomBehaviorRef = useRef(null);
  const tickFrameRef = useRef(null);
  const activeTooltipNodeRef = useRef(null); // Track which node/link the tooltip is showing for
  const timeoutsRef = useRef(new Set()); // Track active timeouts for cleanup
  const lastCenteredSearchRef = useRef('');
  const previousSearchQueryRef = useRef('');
  const userInteractedWithGraphRef = useRef(false);
  const isComponentMountedRef = useMountedRef();
  const graphNodeCountRef = useRef(0);

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
    if (!activeTooltipNodeRef.current) return;
    if (el.style.display === 'none' || el.style.opacity === '0') return;
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
    window.addEventListener('scroll', repositionTooltip, { capture: true, passive: true });
    return () => {
      window.removeEventListener('resize', repositionTooltip);
      window.removeEventListener('scroll', repositionTooltip, true);
    };
  }, [repositionTooltip]);

  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    let spinnerStyleEl = document.head.querySelector('style[data-spinner]');
    if (!spinnerStyleEl) {
      spinnerStyleEl = document.createElement('style');
      spinnerStyleEl.setAttribute('data-spinner', 'true');
      spinnerStyleEl.textContent = `
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `;
      document.head.appendChild(spinnerStyleEl);
    }
    return undefined;
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
        const timeoutId = setTimeout(() => {
          setHighlightedNodeNames(new Set());
          timeoutsRef.current.delete(timeoutId);
        }, HIGHLIGHT_AUTO_CLEAR_MS);
        timeoutsRef.current.add(timeoutId);
      }
    };
    window.addEventListener('dt-highlight-nodes', handler);

    // Pick up any highlight that was queued before this component mounted
    // (e.g. fired from RecommendationsTab before the graph tab was active)
    consumePendingEvents('__dt_pending_highlight').forEach((names) => handler({ detail: { names } }));

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
    const abortController = new AbortController();
    let resultRequestId = 0;
    const loadResultNodes = async (names) => {
      if (!names || names.length === 0) return;
      const requestId = ++resultRequestId;
      clearExpansionState();
      const epoch = expansionEpochRef.current;
      setSearchLoading(true);
      try {
        const response = await graphApi.getOverview(DEFAULT_GRAPH_OVERVIEW_LIMIT, abortController.signal);
        if (!isComponentMountedRef.current || requestId !== resultRequestId || epoch !== expansionEpochRef.current) return;
        const overview = normalizeGraphDataset(response.data);
        const requestedNames = new Set(names.map((name) => normalizeSearchTerm(name)).filter(Boolean));
        const nodes = overview.nodes.filter((node) => requestedNames.has(normalizeSearchTerm(
          node?.properties?.label || node?.label || node?.elementId
        )));
        const nodeIds = new Set(nodes.map(n => n.elementId));
        const links = overview.links.filter((l) => {
          const sourceId = getLinkEndpointId(l.source);
          const targetId = getLinkEndpointId(l.target);
          return nodeIds.has(sourceId) && nodeIds.has(targetId);
        });

        commitGraphSlice({ nodes, links }, {
          updateFilteredData: !graphSearchActiveRef.current,
          updateSearchResultData: true, preserveIsolatedNodes: true,
          syncResults: true, forceSearchResults: true,
        });
      } catch (err) {
        if (abortController.signal.aborted || err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED' || err?.name === 'AbortError') return;
        logger.error('[dt-load-result-nodes] Error:', err.message);
      } finally {
        if (isComponentMountedRef.current && requestId === resultRequestId && epoch === expansionEpochRef.current) {
          setSearchLoading(false);
        }
      }
    };

    const handler = (e) => {
      const names = e.detail?.names;
      if (Array.isArray(names) && names.length > 0) loadResultNodes(names);
    };

    window.addEventListener('dt-load-result-nodes', handler);
    // Pick up any pending load queued before this component processed the event
    consumePendingEvents('__dt_pending_result_nodes').forEach((names) => loadResultNodes(names));
    return () => {
      window.removeEventListener('dt-load-result-nodes', handler);
      abortController.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    const listMatches = responseText.matchAll(/(?:^|\n)\s*[-ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢]\s*\*?\*?([A-Z][A-Za-z0-9_\-. ]{2,50})/g);
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
      timeoutsRef.current.delete(highlightTimeoutId);
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

  // Performance: Optimize state management
  const [investigationNodeId, setInvestigationNodeId] = useState(null);
  const [overviewPresentation, setOverviewPresentation] = useState('groups');
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [filteredData, setFilteredData] = useState({ nodes: [], links: [] });
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  // Performance: Add loading states for better UX
  const [searchLoading, setSearchLoading] = useState(false);
  const [isLayoutSwitching] = useState(false);
  useEffect(() => {
    graphNodeCountRef.current = Array.isArray(graphData?.nodes) ? graphData.nodes.length : 0;
  }, [graphData]);
  // New state for expand/collapse functionality
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [loadingNodes, setLoadingNodes] = useState(new Set());
  const [, setFullDataset] = useState({ nodes: [], links: [] });
  // New state to track initial data for reset functionality
  const [initialData, setInitialData] = useState({ nodes: [], links: [] });
  // Track which nodes were added by each expansion
  const [nodeExpansions, setNodeExpansions] = useState(new Map());
  // Unified primary button color (match WhereUsedView request)

  const [highlightedNodeNames, setHighlightedNodeNames] = useState(new Set());

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
      expansionEpochRef.current += 1;
      expansionRequestsRef.current.forEach(controller => controller.abort());
      expansionRequestsRef.current.clear();
      rootLoadRef.current?.abort();
      rootLoadRef.current = null;
      expansionBaseRef.current = null;
      const clearedExpanded = new Set();
      const clearedExpansions = new Map();
      const clearedLoading = new Set();
      setExpandedNodes(clearedExpanded);
      setNodeExpansions(clearedExpansions);
      setLoadingNodes(clearedLoading);
      expandedNodesRef.current = clearedExpanded;
      nodeExpansionsRef.current = clearedExpansions;
      loadingNodesRef.current = clearedLoading;
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
  const loadingNodesRef = useRef(loadingNodes);
  const activeSearchResultIdRef = useRef(null);
  const contextualRootNodeIdRef = useRef(null);
  const searchModeRef = useRef(false);
  const expandedNodesRef = useRef(new Set());
  const nodeExpansionsRef = useRef(new Map());
  const expansionBaseRef = useRef(null);
  const expansionRequestsRef = useRef(new Map());
  const expansionEpochRef = useRef(0);
  const rootLoadRef = useRef(null);
  const simulationLayoutRef = useRef('');
  const contextualSearchRequestIdRef = useRef(0);

  const stepPartsRequestIdRef = useRef(0);

  // ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ Graph View Mode: 'ontology' = Ontology Graph Visualization, 'individual' = Contextual Individual Graph View
  const [graphViewMode, setGraphViewMode] = useState('ontology');
  const graphViewModeRef = useRef('ontology');
  // Ontology viewer state
  const [selectedOntology, setSelectedOntology] = useState('ALL');
  const selectedOntologyRef = useRef('ALL');
  const lastSpecificOntologyRef = useRef('ALL');
  const lastNeo4jConnectedRef = useRef(null);
  // Local loading state for ontology-specific operations (separate from context loading)

  const [contextualSearchWarning, setContextualSearchWarning] = useState('');
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
    setSearchQuery(String(nextQuery || '').trim());
  }, []);
  // Performance: Memoized search function
  const nodeSearchFunction = useMemo(() => createNodeSearchFunction(), []);
  const graphSearchActive = useMemo(
    () => Boolean(normalizeSearchTerm(searchQuery) || normalizeSearchTerm(debouncedSearchQuery)),
    [searchQuery, debouncedSearchQuery]
  );
  const graphSearchActiveRef = useRef(graphSearchActive);
  const isOntologyGraphMode = graphViewMode === 'ontology' && selectedOntology !== 'ALL';
  const isFullGraphMode = graphViewMode === 'ontology' && selectedOntology === 'ALL';
  const emptyGraphDataset = useMemo(() => ({ nodes: [], links: [] }), []);
  const baseGraphDataset = useMemo(() => {
    if (graphViewMode === 'individual') {
      return filteredData?.nodes?.length || filteredData?.links?.length
        ? filteredData
        : emptyGraphDataset;
    }

    if (isFullGraphMode) {
      return graphData?.nodes?.length || graphData?.links?.length
        ? graphData
        : (initialData?.nodes?.length || initialData?.links?.length ? initialData : emptyGraphDataset);
    }

    if (isOntologyGraphMode) {
      return graphData?.nodes?.length || graphData?.links?.length
        ? graphData
        : emptyGraphDataset;
    }

    return graphData?.nodes?.length || graphData?.links?.length
      ? graphData
      : emptyGraphDataset;
  }, [emptyGraphDataset, filteredData, graphData, graphViewMode, initialData, isFullGraphMode, isOntologyGraphMode]);
  const activeDisplayData = useMemo(() => {
    if (graphViewMode === 'individual') {
      return baseGraphDataset;
    }

    if (graphSearchActive) {
      return searchResultData?.nodes?.length > 0
        ? searchResultData
        : emptyGraphDataset;
    }

    return baseGraphDataset;
  }, [baseGraphDataset, emptyGraphDataset, graphSearchActive, graphViewMode, searchResultData]);
  const activeGraphDataset = useMemo(() => {
    if (graphSearchActive) {
      return baseGraphDataset;
    }
    return activeDisplayData?.nodes?.length || activeDisplayData?.links?.length
      ? activeDisplayData
      : baseGraphDataset;
  }, [activeDisplayData, baseGraphDataset, graphSearchActive]);
  const ontologySliceSummary = useMemo(() => {
    if (graphViewMode !== 'ontology') {
      return null;
    }

    const summaryDataset = graphSearchActive ? activeDisplayData : activeGraphDataset;
    const nodes = Array.isArray(summaryDataset?.nodes) ? summaryDataset.nodes : [];
    const links = Array.isArray(summaryDataset?.links) ? summaryDataset.links : [];
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

    const totalCounts = graphSearchActive ? null : (activeGraphDataset?.view?.total_counts || graphData?.view?.total_counts || null);
    const semanticFamilyCounts = nodes.reduce((acc, node) => {
      const family = getNodeSemanticFamily(node);
      acc[family] = (acc[family] || 0) + 1;
      return acc;
    }, {});
    const visibleFamilies = Object.entries(semanticFamilyCounts)
      .sort((left, right) => right[1] - left[1])
      .slice(0, selectedOntology === 'ALL' ? 6 : 4)
      .map(([label, count]) => ({ label, count }));

    return {
      modeLabel: graphSearchActive ? 'Search results' : (selectedOntology === 'ALL' ? 'Visible overview slice' : 'Current schema slice'),
      nodeCount: nodes.length,
      relationshipCount: links.length,
      visibleRelationships,
      visibleSchemaLabels,
      hasSubclassEdges: Boolean(relationshipCounts.SUBCLASS_OF),
      visibleFamilies,
      totalCounts,
      isCapped: Boolean(totalCounts && (totalCounts.nodes > nodes.length || totalCounts.relationships > links.length)),
    };
  }, [activeDisplayData, activeGraphDataset, graphData, graphSearchActive, graphViewMode, selectedOntology]);

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
    if (!clear && graphSearchActiveRef.current && !force) {
      return;
    }
    setSearchResults(nodes);
  }, [setSearchResults]);

  const clearExpansionState = useCallback(() => {
    expansionEpochRef.current += 1;
    expansionRequestsRef.current.forEach(controller => controller.abort());
    expansionRequestsRef.current.clear();
    rootLoadRef.current?.abort();
    rootLoadRef.current = null;
    expansionBaseRef.current = null;
    const clearedExpanded = new Set();
    const clearedExpansions = new Map();
    const clearedLoading = new Set();
    setExpandedNodes(clearedExpanded);
    setNodeExpansions(clearedExpansions);
    setLoadingNodes(clearedLoading);
    expandedNodesRef.current = clearedExpanded;
    nodeExpansionsRef.current = clearedExpansions;
    loadingNodesRef.current = clearedLoading;
  }, []);

  useEffect(() => {
    clearExpansionState();
  }, [debouncedSearchQuery, graphViewMode, selectedOntology, selectedStepPart, clearExpansionState]);

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

  const buildSearchResultSlice = useCallback((baseData, query) => searchLoadedGraph(baseData, query), []);

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
      preserveIsolatedNodes = false,
    } = options;

    const normalizedSlice = deduplicateNodesAndLinks(nextData?.nodes || [], nextData?.links || []);
    const validatedSlice = validateConnectivity(normalizedSlice);
    if (preserveIsolatedNodes) {
      if (validatedSlice.orphanNodeIds.length > 0 && isDevelopment) {
        performanceWarn('[GRAPH] commitGraphSlice preserving isolated nodes:', validatedSlice.orphanNodeIds);
      }
      if (updateFilteredData) { filteredDataRef.current = normalizedSlice; setFilteredData(normalizedSlice); }
      setData(normalizedSlice);
      if (updateGraphData) setGraphData(normalizedSlice);
      if (updateFullDataset) setFullDataset(normalizedSlice);
      if (updateSearchResultData) { searchResultDataRef.current = normalizedSlice; setSearchResultData(normalizedSlice); }

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
        syncSharedSearchResults(normalizedSlice.nodes || [], { force: forceSearchResults });
      }
      return;
    }
    const graphNodeCap = Math.max(1, Number(API?.ui?.graphMaxNodes) || 750);
    const nodeList = normalizedSlice.nodes || [];
    const linkList = normalizedSlice.links || [];
    const nodeDegree = new Map(nodeList.map((node) => [node.elementId, 0]));
    linkList.forEach((link) => {
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      if (sourceId && nodeDegree.has(sourceId)) nodeDegree.set(sourceId, (nodeDegree.get(sourceId) || 0) + 1);
      if (targetId && nodeDegree.has(targetId)) nodeDegree.set(targetId, (nodeDegree.get(targetId) || 0) + 1);
    });
    const cappedNodes = nodeList
      .slice()
      .sort((left, right) => {
        const rightDegree = nodeDegree.get(right.elementId) || 0;
        const leftDegree = nodeDegree.get(left.elementId) || 0;
        if (rightDegree !== leftDegree) return rightDegree - leftDegree;
        return String(left.elementId || '').localeCompare(String(right.elementId || ''));
      })
      .slice(0, graphNodeCap);
    const allowedNodeIds = new Set(cappedNodes.map((node) => node.elementId));
    const cappedLinks = linkList.filter((link) => {
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      return allowedNodeIds.has(sourceId) && allowedNodeIds.has(targetId);
    });
    const connectedNodeIds = new Set();
    cappedLinks.forEach((link) => {
      const sourceId = getLinkEndpointId(link.source);
      const targetId = getLinkEndpointId(link.target);
      if (sourceId) connectedNodeIds.add(sourceId);
      if (targetId) connectedNodeIds.add(targetId);
    });
    const prunedSlice = {
      nodes: cappedNodes.filter((node) => connectedNodeIds.has(node.elementId)),
      links: cappedLinks.filter((link) => {
        const sourceId = getLinkEndpointId(link.source);
        const targetId = getLinkEndpointId(link.target);
        return connectedNodeIds.has(sourceId) && connectedNodeIds.has(targetId);
      }),
    };
    if (validatedSlice.orphanNodeIds.length > 0 && isDevelopment) {
      performanceWarn('[GRAPH] commitGraphSlice orphan nodes detected:', validatedSlice.orphanNodeIds);
    }

    if (updateFilteredData) { filteredDataRef.current = prunedSlice; setFilteredData(prunedSlice); }
    setData(prunedSlice);
    if (updateGraphData) setGraphData(prunedSlice);
    if (updateFullDataset) setFullDataset(prunedSlice);
    if (updateSearchResultData) { searchResultDataRef.current = prunedSlice; setSearchResultData(prunedSlice); }

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

    clearExpansionState();
    const controller = new AbortController();
    rootLoadRef.current = controller;
    setSearchLoading(true);
    try {
      const traversalDepth = 3;
      const response = await graphApi.getTraversal(nodeId, traversalDepth, controller.signal);
      if (controller.signal.aborted || rootLoadRef.current !== controller || !isComponentMountedRef.current) return;
      const traversalData = normalizeGraphDataset(response.data, { collapseHiddenBridges: true });
      const rootedData = sanitizeContextualGraph(traversalData, nodeId);

      contextualRootNodeIdRef.current = nodeId;
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
        preserveIsolatedNodes: true,
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
      if (controller.signal.aborted || !isComponentMountedRef.current) return;
      logger.error('[CONTEXTUAL SEARCH] Failed to load selected root graph:', loadError);
      setError('Unable to load the selected context. The graph shown is the previous snapshot; retry the selected root.');
    } finally {
      if (rootLoadRef.current === controller) {
        rootLoadRef.current = null;
        if (isComponentMountedRef.current) setSearchLoading(false);
      }
    }
  }, [clearExpansionState, commitGraphSlice, syncContextualHighlights, syncSharedSearchResults]);

  const loadContextualSearchMatch = useCallback(async (matches, query, requestId, sourceGraph = null) => {
    const dedupedMatches = matches.filter((node, index, array) => (
      array.findIndex((entry) => entry.elementId === node.elementId) === index
    ));
    const preferredMatchId = findPreferredContextualRootId(dedupedMatches, query);
    const bestMatchId = preferredMatchId || dedupedMatches[0]?.elementId || null;

    if (requestId !== contextualSearchRequestIdRef.current) return;
    if (!bestMatchId) {
      rootLoadRef.current?.abort();
      rootLoadRef.current = null;
      clearExpansionState();
      setContextualRootNodeId(null);
      contextualRootNodeIdRef.current = null;
      setInvestigationNodeId(null);
      hideAllTooltips();
      commitGraphSlice({nodes: [], links: []}, {
        updateGraphData: false, updateFullDataset: false,
        updateFilteredData: true, updateSearchResultData: true,
        clearActiveSearchId: true, syncResults: true,
      });
      setContextualSearchResults([]);
      setHighlightedNodeIds(new Set());
      setSearchLoading(false);
      return;
    }

    setContextualSearchResults([]);
    const matchIds = new Set(dedupedMatches.map((node) => node.elementId).filter(Boolean));
    const searchCatalog = {
      nodes: dedupedMatches,
      links: (sourceGraph?.links || []).filter((link) => {
        const sourceId = getLinkEndpointId(link?.source);
        const targetId = getLinkEndpointId(link?.target);
        return matchIds.has(sourceId) && matchIds.has(targetId);
      }),
    };
    searchResultDataRef.current = searchCatalog;
    setSearchResultData(searchCatalog);
    setContextualRootNodeId(bestMatchId);

    setHighlightedNodeIds(new Set(matchIds));
    await loadContextualRootGraph(bestMatchId, { preserveSearch: true });
  }, [findPreferredContextualRootId, loadContextualRootGraph, clearExpansionState, commitGraphSlice]);

  const resolveContextualEntryNodeId = useCallback((queryOverride = '') => {
    const queryTerm = normalizeSearchTerm(queryOverride || debouncedSearchQueryRef.current || searchInput || searchQuery);
    const candidateMap = new Map();

    const allowSchemaFallbackNodes = searchResultDataRef.current?.view?.fallback === 'schema'
      || filteredDataRef.current?.view?.fallback === 'schema';

    [...(searchResultDataRef.current?.nodes || []), ...(filteredDataRef.current?.nodes || [])]
      .filter((node) => (
        node?.elementId
        && !isMetadataWrapperNode(node)
        && !isRelationshipCarrierNode(node)
        && (allowSchemaFallbackNodes || !isSchemaTerminalNode(node))
      ))
      .forEach((node) => {
        if (!candidateMap.has(node.elementId)) {
          candidateMap.set(node.elementId, node);
        }
      });

    if (activeSearchResultIdRef.current && candidateMap.has(activeSearchResultIdRef.current)) {
      return activeSearchResultIdRef.current;
    }
    if (contextualRootNodeIdRef.current && candidateMap.has(contextualRootNodeIdRef.current)) {
      return contextualRootNodeIdRef.current;
    }

    const candidates = Array.from(candidateMap.values());
    if (candidates.length === 0) return null;
    return findBestSearchMatchId(candidates, queryTerm) || candidates[0]?.elementId || null;
  }, [findBestSearchMatchId, searchInput, searchQuery]);

  const preferredOntologyValue = useMemo(() => {
    if (selectedOntology && selectedOntology !== 'ALL') return selectedOntology;
    const candidates = (ontologyOptions || []).filter((option) => option?.value && option.value !== 'ALL');
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
    loadingNodesRef.current = loadingNodes;
  }, [loadingNodes]);
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
    const nodeLabels = Array.isArray(nodeLike?.labels) ? nodeLike.labels.map((entry) => String(entry || '')) : [];
    const subtypeKey = resolveNodeColorKey(nodeLike);
    const displayName = resolveNodeName(nodeLike);
    const normalizedLabel = String(subtypeKey || label).toLowerCase();
    const hashSeed = (() => {
      const baseKey = String(subtypeKey || label || 'Node').toLowerCase();
      const genericType = ['ontologyclass', 'class', 'individual', 'resource', 'node', 'entity', 'item'].includes(baseKey);
      if (genericType && displayName) return `${baseKey}:${displayName}`;
      return subtypeKey || label;
    })();

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
      'Requirement':       '#7C3AED',
      'RequirementRevision':'#6D28D9',
      'Specification':     '#5B21B6',
      'Document':          '#0F766E',
      'Package':           '#0E7490',
      'View':              '#BE185D',

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
      'MetadataAsset':     '#0F766E',
      'GeneralRelation':   '#C05621',
    };

    const explicitColor = colorMap[subtypeKey] || colorMap[label];
    const variantSeed = `${subtypeKey || label}:${displayName || hashSeed}`;
    const isOntologyClassFamily = label === 'OntologyClass' || nodeLabels.includes('OntologyClass');
    const isObjectPropertyFamily = ['ObjectProperty', 'OntologyProperty', 'Property'].includes(label) || nodeLabels.includes('ObjectProperty');
    const isDatatypePropertyFamily = label === 'DatatypeProperty' || nodeLabels.includes('DatatypeProperty');
    if (isOntologyClassFamily) {
      return pickPaletteColor(ONTOLOGY_CLASS_PALETTE, variantSeed);
    }
    if (isObjectPropertyFamily) {
      return pickPaletteColor(OBJECT_PROPERTY_PALETTE, variantSeed);
    }
    if (isDatatypePropertyFamily) {
      return pickPaletteColor(DATATYPE_PROPERTY_PALETTE, variantSeed);
    }
    if (explicitColor) {
      return varyColorBySeed(explicitColor, variantSeed, {
        lightnessRange: ['OntologyClass', 'ObjectProperty', 'DatatypeProperty', 'Property'].includes(label) ? 16 : 12,
        saturationBoost: ['OntologyClass', 'ObjectProperty', 'DatatypeProperty', 'Property'].includes(label) ? 6 : 0,
      });
    }

    if (normalizedLabel.includes('property')) return '#0E7490';
    if (normalizedLabel.includes('class')) return '#1F3D63';
    if (normalizedLabel.includes('assembly') || normalizedLabel.includes('bom')) return '#2F855A';
    if (normalizedLabel.includes('product')) return '#274C77';
    if (normalizedLabel.includes('part')) return '#355C7D';
    if (normalizedLabel.includes('requirement')) return '#7C3AED';
    if (normalizedLabel.includes('document')) return '#0F766E';
    if (normalizedLabel.includes('process')) return '#C05621';
    if (normalizedLabel.includes('geometry') || normalizedLabel.includes('shape') || normalizedLabel.includes('cad')) return '#8D6E63';
    if (normalizedLabel.includes('material')) return '#A16207';
    if (normalizedLabel.includes('organization') || normalizedLabel.includes('person')) return '#BE185D';
    if (normalizedLabel.includes('instance')) return '#486581';
    if (normalizedLabel.includes('metadata')) return '#0F766E';
    if (normalizedLabel.includes('generalrelation') || normalizedLabel.includes('trace')) return '#C05621';

    return ENTITY_COLOR_SWATCH[hashText(hashSeed) % ENTITY_COLOR_SWATCH.length];
  }, []);

  const getNodeLabelColor = useCallback(() => TCS_GRAPH_THEME.ink, []);

  const getRelationshipLabelColor = useCallback(() => TCS_GRAPH_THEME.inkSoft, []);

  // Primary label logic used in force-directed graph labels.
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

  // Prefer true data-bearing fields; do not surface driver metadata or knowledge graph labels.
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
    userInteractedWithGraphRef.current = true;
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

  const handleZoom = useCallback(({ transform, sourceEvent }) => {
    if (sourceEvent) userInteractedWithGraphRef.current = true;
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
        const response = await graphApi.getOverview(DEFAULT_GRAPH_OVERVIEW_LIMIT, abortController.signal);

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
                updateFilteredData: !graphSearchActiveRef.current,
                updateSearchResultData: !graphSearchActiveRef.current,
                syncResults: !graphSearchActiveRef.current,
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

  // Monitor knowledge graph connection health and refresh graph if reconnected
  useEffect(() => {
    let active = true;
    let controller = null;
    const checkHealth = async () => {
      controller = new AbortController();
      try {
        const response = await platformAPI.health('graph', { signal: controller.signal });
        if (!active) return;
        const connected = response.data?.status === 'ok';
        const previousConnected = lastNeo4jConnectedRef.current;
        lastNeo4jConnectedRef.current = connected;

        if (
          connected &&
          previousConnected === false &&
          graphNodeCountRef.current === 0 &&
          !normalizeSearchTerm(debouncedSearchQueryRef.current) &&
          !graphSearchActiveRef.current &&
          !userInteractedWithGraphRef.current &&
          graphViewModeRef.current === 'ontology' &&
          selectedOntologyRef.current === 'ALL'
        ) {
          // Connection was restored but graph is empty - trigger refresh
          logger.data('knowledge graph reconnected, refreshing graph...');
          const graphResponse = await graphApi.getOverview(DEFAULT_GRAPH_OVERVIEW_LIMIT, controller.signal);
          if (!active) return;
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
        if (err?.name === 'AbortError' || err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
        logger.warn('Health check error:', err.message);
      }
    };

    // Check health every 30 seconds
    const healthCheckInterval = setInterval(checkHealth, 30000);
    return () => {
      active = false;
      clearInterval(healthCheckInterval);
      controller?.abort();
    };
  }, [commitGraphSlice]);

  // Performance: Optimized search with debouncing and caching
  useEffect(() => {
    const isContextualQuery = graphViewModeRef.current === 'individual' || (isFullGraphMode && Boolean(normalizeSearchTerm(debouncedSearchQuery)));

    if (!normalizeSearchTerm(debouncedSearchQuery)) {
      searchModeRef.current = false;
      setSearchLoading(false);
      setContextualSearchResults([]);
      setHighlightedNodeIds(new Set());
      setActiveSearchResultId(null);
      activeSearchResultIdRef.current = null;

      if (isContextualQuery) {
        setSearchResultData({ nodes: [], links: [] });
        if (filteredDataRef.current?.nodes?.length) {
          syncSharedSearchResults(filteredDataRef.current.nodes || []);
          return;
        }
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
      setContextualSearchWarning('');
      syncContextualHighlights(debouncedSearchQuery);
      syncSharedSearchResults([], { clear: true });

      const performContextualSearch = async () => {
        try {
          // ALL means all source instances, never a hidden registry preference.
          const ontologyPrefix = resolveOntologySearchPrefix(selectedOntologyRef.current);
          const response = await graphApi.getContextualSubgraph({
            search: debouncedSearchQuery,
            searchMode: 'best',
            expandNeighbors: false,
            // Keep the backend search broad and object-centric; root context is
            // chosen client-side from the returned matches so it is based on
            // actual knowledge graph hits instead of a premature server-side root guess.
            limit: 24,
            ...(ontologyPrefix ? { ontologyPrefix } : {}),
          }, abortController.signal);

          if (requestId !== contextualSearchRequestIdRef.current) {
            return;
          }

          const normalized = normalizeGraphDataset(response.data);
          setContextualSearchWarning('');
          const allowSchemaFallbackNodes = normalized?.view?.fallback === 'schema';
          const candidateNodes = normalized.nodes.filter((node) => (
            node?.elementId
            && !isMetadataWrapperNode(node)
            && (allowSchemaFallbackNodes || !isSchemaTerminalNode(node))
          ));
          const ranked = nodeSearchFunction(candidateNodes, debouncedSearchQuery);
          const rankedMatches = ranked.length ? ranked : candidateNodes;
          await loadContextualSearchMatch(rankedMatches, debouncedSearchQuery, requestId, normalized);
        } catch (err) {
          if (abortController.signal.aborted || requestId !== contextualSearchRequestIdRef.current || err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
          logger.error('[CONTEXTUAL SEARCH] Error:', err);
          setContextualSearchWarning('Contextual graph service is unavailable. Results are limited to nodes already loaded in this view.');
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
        const response = await graphApi.searchUniversal(debouncedSearchQuery, {
          scope: selectedOntologyRef.current === 'ALL' ? '' : selectedOntologyRef.current,
          limit: 80,
        }, abortController.signal);
        if (abortController.signal.aborted) return;
        const normalized = normalizeGraphDataset(response.data);
        setOntologyGraphMessage(response.data?.view?.truncated
          ? 'Showing a bounded set of matches in the selected scope. Refine the search to find more specific results.'
          : 'Search covers nodes, relationships, property names and values in the selected scope. Property previews are shortened.');

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
            preserveIsolatedNodes: true,
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
            preserveIsolatedNodes: true,
          });
        });
        }

        // Batch loading state updates
        startTransition(() => {
          setSearchLoading(false);
        });
      } catch (err) {
        // Ignore cancelled requests (superseded by newer search)
        if (abortController.signal.aborted || err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
        setOntologyGraphMessage('Graph search is unavailable. Showing matches only from the loaded view; results may be incomplete.');
        logger.error('Search Error:', err);
        const fallbackGraph = buildSearchResultSlice(resolveSearchBaseDataset(), debouncedSearchQuery);
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
            preserveIsolatedNodes: true,
          });
          setSearchLoading(false);
        });
      }
    };

    performSearch();
    // Cleanup: abort in-flight request when query changes or component unmounts
    return () => abortController.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildSearchResultSlice, commitGraphSlice, debouncedSearchQuery, graphViewMode, isFullGraphMode, isOntologyGraphMode, resolveSearchBaseDataset]);

  const { fetchOntologyGraph, fetchArchitectureGraph, scopeLoading, ontologyGraphMessage, setOntologyGraphMessage } = useGraphData({
    initialData, commitGraphSlice, searchModeRef, searchActiveRef: graphSearchActiveRef, setStepParts, setSelectedStepPart,
    scopeKey: `${graphViewMode}:${selectedOntology}`, limit: DEFAULT_ONTOLOGY_VIEW_LIMIT,
  });
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
    if (!normalizeSearchTerm(debouncedSearchQuery)) {
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
      // Ontology mode ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â restore or refetch based on active ontology selection.
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
        if (selected === 'archimate') {
          fetchArchitectureGraph('archimate');
        } else {
          const part = selected === 'step' ? selectedStepPart : 'ALL';
          fetchOntologyGraph(selected, part);
        }
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

  const previousOntologyScopeRef = useRef(selectedOntology);
  // Callback changes (for example a late overview response) are not a scope
  // change and must not clear a search the user has already submitted.
  useEffect(() => {
    if (graphViewModeRef.current === 'individual') return; // individual mode manages its own data
    const scopeChanged = previousOntologyScopeRef.current !== selectedOntology;
    previousOntologyScopeRef.current = selectedOntology;
    if (scopeChanged) resetGraphSelectionState({ resetOntology: false, resetStepPart: false });

    if (selectedOntology === 'archimate') {
      setStepParts([]);
      setSelectedStepPart('ALL');
      fetchArchitectureGraph('archimate');
      return;
    }

    if (selectedOntology === 'step') {
      const requestId = ++stepPartsRequestIdRef.current;
      // Fetch STEP parts list for secondary filter
      setStepPartsLoading(true);
      setStepPartsError(null);
      graphApi.getStepParts()
        .then(res => {
          if (requestId !== stepPartsRequestIdRef.current) return;
          const parts = res.data?.parts || [];
          setStepParts(parts);
          setSelectedStepPart('ALL');
          if (parts.length === 0) {
            setStepPartsError('No STEP parts available');
          }
        })
        .catch(err => {
          if (requestId !== stepPartsRequestIdRef.current) return;
          const errorMsg = err.response?.data?.detail || err.message || 'Failed to fetch STEP parts';
          setStepPartsError(errorMsg);
          logger.error('[ONTOLOGY] Failed to fetch STEP parts:', err);
        })
        .finally(() => {
          if (requestId === stepPartsRequestIdRef.current) setStepPartsLoading(false);
        });
    } else {
      stepPartsRequestIdRef.current += 1;
      setStepParts([]);
      setSelectedStepPart('ALL');
      setStepPartsError(null);
    }

    fetchOntologyGraph(selectedOntology, 'ALL');
  }, [selectedOntology, fetchOntologyGraph, fetchArchitectureGraph, resetGraphSelectionState]);

  // When STEP part sub-filter changes, fetch that specific part's graph
  useEffect(() => {
    if (graphViewModeRef.current === 'individual') return;
    if (selectedOntology !== 'step') return;
    // Skip if 'ALL' ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â the main ontology useEffect already handles that
    if (selectedStepPart === 'ALL') return;
    fetchOntologyGraph('step', selectedStepPart);
  }, [selectedStepPart, selectedOntology, fetchOntologyGraph]);

  // Function to determine if a node has expandable connections
  const hasExpandableConnections = (nodeData) => {
    // Allow expansion in contextual-instance mode even without an active search.
    const isNotExpanded = !expandedNodesRef.current.has(nodeData.elementId);
    const hasSearchQuery = graphSearchActiveRef.current || !!debouncedSearchQueryRef.current;
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
    const hasSearchQuery = graphSearchActiveRef.current || !!debouncedSearchQueryRef.current; // Use live active search state
    const isContextualMode = graphViewModeRef.current === 'individual';

    return (hasSearchQuery || isContextualMode) && isExpanded;
  };

  // Function to expand a node using graphtraverse API - 1-2 hop expansion
  const expandNode = async (nodeId) => {
    if (!nodeId || expandedNodesRef.current.has(nodeId) || expansionRequestsRef.current.has(nodeId)) return;
    const initialSlice = getCurrentGraphSlice();
    if (!initialSlice.nodes.some(node => node.elementId === nodeId)) return;
    if (!expansionBaseRef.current) expansionBaseRef.current = initialSlice;
    const epoch = expansionEpochRef.current;
    const scope = JSON.stringify([graphViewModeRef.current, selectedOntologyRef.current, debouncedSearchQueryRef.current]);
    const controller = new AbortController();
    expansionRequestsRef.current.set(nodeId, controller);
    const loading = new Set(expansionRequestsRef.current.keys());
    loadingNodesRef.current = loading;
    setLoadingNodes(loading);
    try {
      const response = await graphApi.getTraversal(nodeId, (graphViewModeRef.current === 'individual' || selectedOntologyRef.current === 'ALL') ? 3 : 1, controller.signal);
      if (controller.signal.aborted || !isComponentMountedRef.current || epoch !== expansionEpochRef.current
          || scope !== JSON.stringify([graphViewModeRef.current, selectedOntologyRef.current, debouncedSearchQueryRef.current])) return;
      const latest = getCurrentGraphSlice();
      if (!latest.nodes.some(node => node.elementId === nodeId)) return;
      const businessContext = graphViewModeRef.current === 'individual' || (selectedOntologyRef.current === 'ALL' && graphSearchActiveRef.current);
      const normalized = normalizeGraphDataset(response.data, { collapseHiddenBridges: true });
      const context = businessContext ? sanitizeContextualGraph(normalized, nodeId) : normalized;
      const slice = boundExpansionSlice(latest, context, DEFAULT_GRAPH_OVERVIEW_LIMIT);
      if (!slice.nodes.some(node => node.elementId === nodeId)) {
        setError('No traversal data was returned for this node. The displayed graph is unchanged.');
        return;
      }
      const expansions = new Map(nodeExpansionsRef.current);
      expansions.set(nodeId, slice);
      const rebuilt = rebuildExpandedGraph(expansionBaseRef.current, expansions);
      nodeExpansionsRef.current = rebuilt.expansions;
      expandedNodesRef.current = new Set(rebuilt.expansions.keys());
      setNodeExpansions(rebuilt.expansions);
      setExpandedNodes(expandedNodesRef.current);
      commitGraphSlice(rebuilt.graph, {
        updateSearchResultData: true, updateGraphData: !graphSearchActiveRef.current && graphViewModeRef.current !== 'individual',
        updateFullDataset: !graphSearchActiveRef.current && graphViewModeRef.current !== 'individual',
        preserveIsolatedNodes: true, syncResults: true, forceSearchResults: true,
      });
      setError(slice.truncated ? `Graph display limit (${DEFAULT_GRAPH_OVERVIEW_LIMIT} nodes) reached. Collapse a branch or narrow the search to explore further.` : null);
    } catch (loadError) {
      if (!controller.signal.aborted && epoch === expansionEpochRef.current && isComponentMountedRef.current) {
        logger.error('Error expanding node:', nodeId, loadError);
        setError('Unable to expand this node. Check graph service access and retry; the graph is unchanged.');
      }
    } finally {
      if (expansionRequestsRef.current.get(nodeId) === controller) {
        expansionRequestsRef.current.delete(nodeId);
        const remaining = new Set(expansionRequestsRef.current.keys());
        loadingNodesRef.current = remaining;
        if (isComponentMountedRef.current) setLoadingNodes(remaining);
      }
    }
  };

  const collapseNode = (nodeId) => {
    if (!nodeExpansionsRef.current.has(nodeId) || !expansionBaseRef.current) return;
    const rebuilt = rebuildExpandedGraph(expansionBaseRef.current, nodeExpansionsRef.current, nodeId);
    const visible = new Set(rebuilt.graph.nodes.map(node => node.elementId));
    expansionRequestsRef.current.forEach((controller, root) => {
      if (root === nodeId || !visible.has(root)) {
        controller.abort();
        expansionRequestsRef.current.delete(root);
      }
    });
    const loading = new Set(expansionRequestsRef.current.keys());
    loadingNodesRef.current = loading;
    setLoadingNodes(loading);
    nodeExpansionsRef.current = rebuilt.expansions;
    expandedNodesRef.current = new Set(rebuilt.expansions.keys());
    setNodeExpansions(rebuilt.expansions);
    setExpandedNodes(expandedNodesRef.current);
    commitGraphSlice(rebuilt.graph, {
      updateSearchResultData: true, updateGraphData: !graphSearchActiveRef.current && graphViewModeRef.current !== 'individual',
      updateFullDataset: !graphSearchActiveRef.current && graphViewModeRef.current !== 'individual',
      preserveIsolatedNodes: true, syncResults: true, forceSearchResults: true,
    });
  };

  // Function to initialize node positions around center
  const initializeNodePositions = (nodes, width, height) => seedSimulationNodes(nodes, width, height);

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

  // Separate effect: apply/remove "View in Graph" highlights via direct D3 DOM manipulation
  // This avoids re-rendering the entire graph just to toggle highlights
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    const hasHighlights = highlightedNodeNames.size > 0;

    // Force-directed layout: add/remove glow rings on .node-group circles
    svg.selectAll('.node-group').each(function(d) {
      const group = d3.select(this);
      const isHighlighted = hasHighlights && buildNodeHighlightTerms(d).some((term) => highlightedNodeNames.has(term));

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
    });  }, [highlightedNodeNames]);

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
        .attr('fill', getNodeLabelColor(d));
    });
  }, [highlightedNodeIds]);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    const currentNodeCount = Array.isArray(activeDisplayData?.nodes) ? activeDisplayData.nodes.length : 0;
    const currentLinkCount = Array.isArray(activeDisplayData?.links) ? activeDisplayData.links.length : 0;
    const baseOpacity = getVisibleRelationshipOpacity(currentNodeCount, currentLinkCount);

    svg.selectAll('.link').each(function(d) {
      const sourceId = getLinkEndpointId(d?.source);
      const targetId = getLinkEndpointId(d?.target);
      const sourceNameHighlighted = highlightedNodeNames.size > 0
        && buildNodeHighlightTerms(d?.source).some((term) => highlightedNodeNames.has(term));
      const targetNameHighlighted = highlightedNodeNames.size > 0
        && buildNodeHighlightTerms(d?.target).some((term) => highlightedNodeNames.has(term));
      const isHighlighted = highlightedNodeIds.has(sourceId)
        || highlightedNodeIds.has(targetId)
        || activeSearchResultId === sourceId
        || activeSearchResultId === targetId
        || sourceNameHighlighted
        || targetNameHighlighted;
      const visual = getRelationshipVisual(d?.type);
      const baseWidth = getVisibleRelationshipStrokeWidth(d?.type, currentNodeCount, currentLinkCount);

      d3.select(this)
        .classed('highlighted', isHighlighted)
        .attr('stroke', isHighlighted ? '#ff6600' : visual.color)
        .attr('stroke-opacity', isHighlighted ? 1 : baseOpacity)
        .attr('stroke-width', isHighlighted ? Math.max(3, baseWidth + 0.6) : baseWidth);
    });
  }, [activeDisplayData, activeSearchResultId, highlightedNodeIds, highlightedNodeNames]);
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('.node-group').each(function(d) {
      const group = d3.select(this);
      const isActive = activeSearchResultId === d?.elementId;
      const isMatch = highlightedNodeIds.has(d?.elementId);

      group.select('.search-active-ring')
        .style('opacity', isActive ? 1 : 0)
        .attr('stroke', isActive ? TCS_GRAPH_THEME.primary : 'none');

      group.select('.node-label')
        .attr('fill', getNodeLabelColor(d));

      if (isActive) {
        group.raise();
      }
    });
  }, [activeSearchResultId, highlightedNodeIds]);
  // Keyboard shortcuts for expand/collapse
  useEffect(() => {
    const handleKeyPress = (event) => {
      if (event.key === 'Escape' && !event.defaultPrevented
          && !event.target?.closest?.('input, textarea, select, [contenteditable="true"]')) {
        const originalSlice = expansionBaseRef.current || getCurrentGraphSlice();
        resetGraphSelectionState({ resetOntology: false, resetStepPart: false, resetSearch: false });
        commitGraphSlice(originalSlice, {
          updateSearchResultData: true, preserveIsolatedNodes: true,
          syncResults: true, forceSearchResults: true,
        });
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commitGraphSlice, getCurrentGraphSlice, resetGraphSelectionState]);

  // Clearing the search also clears branch ownership for the previous result.
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
      expansionEpochRef.current += 1;
      expansionRequestsRef.current.forEach(controller => controller.abort());
      expansionRequestsRef.current.clear();
      rootLoadRef.current?.abort();
      // Stop D3 simulation if running
      if (simulationRef.current) {
        simulationRef.current.stop();
        simulationRef.current = null;
      }
    };
  }, []);

  const investigationNode = activeDisplayData?.nodes?.find(node => node.elementId === (investigationNodeId || activeSearchResultId)) || null;

  return (
    <div
      className="graph-heb-container graph-heb-root"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: 0,
        minWidth: 0,
        background: TCS_GRAPH_THEME.surfaceMuted,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* STATIC TOOLBAR (prevents overlap with graph canvas) */}
      <GraphFilters
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
        onToolTargetSelect={(target) => {
          if (typeof setActiveTab === 'function') setActiveTab(target);
        }}
        onOpenFullGraph={() => {
          setOntologyGraphMessage('');
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
          const nextOntology = lastSpecificOntologyRef.current !== 'ALL' && lastSpecificOntologyRef.current !== 'archimate'
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
        onOpenArchitectureGraph={() => {
          setOntologyGraphMessage('');
          setGraphViewMode('ontology');
          graphViewModeRef.current = 'ontology';
          setSelectedOntology('archimate');
          selectedOntologyRef.current = 'archimate';
          lastSpecificOntologyRef.current = 'archimate';
        }}
        onOpenContextualGraph={() => {
          setOntologyGraphMessage('');
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
        ontologyLoading={ontologyLoading || scopeLoading}
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
          setOntologyGraphMessage('');
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
      {(isLoading || scopeLoading) && (
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
          <div style={{ marginBottom: '16px', fontSize: '48px', color: '#C0392B' }}><i className="fas fa-exclamation-triangle"></i></div>
          <div style={{ fontSize: '18px', fontWeight: '600', color: '#C0392B', marginBottom: '8px' }}>Connection Error</div>
          <div style={{ fontSize: '14px', color: '#7f8c8d' }}>{error}</div>
        </div>
      )}
      {!isLoading && !scopeLoading && !error && contextualSearchWarning && (
        <div role="status" style={{ position: 'absolute', top: 72, left: '50%', transform: 'translateX(-50%)', zIndex: 12, padding: '8px 12px', borderRadius: 4, background: '#fff4ce', color: '#5c4400', border: '1px solid #e4c45b' }}>
          {contextualSearchWarning}
        </div>
      )}
      {!isLoading && !scopeLoading && !error && graphViewMode !== 'individual' && graphSearchActive && !searchLoading && normalizeSearchTerm(debouncedSearchQuery) && searchResultData.nodes.length === 0 && (
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
      {!isLoading && !scopeLoading && !error && graphViewMode !== 'individual' && activeGraphDataset.nodes.length === 0 && !searchQuery && (
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
          <div style={{ fontSize: '18px', fontWeight: '600', color: '#2C2C2C', marginBottom: '8px' }}>
            {isOntologyGraphMode ? 'No Ontology Graph Available' : 'No Graph Data Available'}
          </div>
          <div style={{ fontSize: '14px', color: '#7f8c8d' }}>
            {isOntologyGraphMode
              ? (ontologyGraphMessage || 'The selected ontology did not return classes or relationships for visualization.')
              : 'No graph data available from knowledge graph database'}
          </div>
        </div>
      )}
      {!isLoading && !scopeLoading && !error && graphViewMode === 'individual' && !searchLoading && activeGraphDataset.nodes.length === 0 && (
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
          {normalizeSearchTerm(debouncedSearchQuery) ? (
            <>
              <div style={{ marginBottom: '12px', fontSize: '18px', fontWeight: 700, color: '#2C2C2C' }}>No Results Found</div>
              <div style={{ fontSize: '13px', color: '#7f8c8d', marginBottom: '4px' }}>No connected instance nodes matched <strong>"{debouncedSearchQuery}"</strong>.</div>
              <div style={{ fontSize: '12px', color: '#95a5a6' }}>Try a broader business term, class name, property value, or wildcard prefix such as <strong>REQ-*</strong>.</div>
            </>
          ) : (
            <>
              <div style={{ marginBottom: '12px', fontSize: '18px', fontWeight: 700, color: '#2C2C2C' }}>Contextual Instance Graph</div>
              <div style={{ fontSize: '13px', color: '#7f8c8d', marginBottom: '4px' }}>Search for an instance to load a bounded three-hop source neighborhood.</div>
              <div style={{ fontSize: '12px', color: '#95a5a6' }}>Master/revision records and explicit trace-link records remain separate. Expand a node to explore another bounded neighborhood.</div>
            </>
          )}
        </div>
      )}

  {graphSearchActive && (graphViewMode === 'individual' || selectedOntology === 'ALL') && <p style={{padding:'8px 16px',margin:0}}>Connected business context around the selected match. Source-path connections retain their relationship-record IDs; they are not inferred direct relationships.</p>}
  <GraphInvestigation node={investigationNode} ontologyId={selectedOntology} nodeCount={activeDisplayData?.nodes?.length || 0} relationshipCount={activeDisplayData?.links?.length || 0} />
  {graphViewMode === 'ontology' && selectedOntology === 'ALL' && !graphSearchActive && <div className="graph-presentation-controls" role="group" aria-label="Overview presentation"><button aria-pressed={overviewPresentation==='groups'} onClick={()=>setOverviewPresentation('groups')}>Grouped overview</button><button aria-pressed={overviewPresentation==='entities'} onClick={()=>setOverviewPresentation('entities')}>Entity graph</button></div>}
  {graphViewMode === 'ontology' && selectedOntology === 'ALL' && !graphSearchActive && overviewPresentation === 'groups' ? <OntologyGroupOverview data={activeDisplayData} ontologyOptions={ontologyOptions} onInspectNode={setInvestigationNodeId} onOpenOntology={id=>setSelectedOntology(id)}/> : <GraphCanvas ref={svgRef}
        model={{ filteredData, graphSearchActive, activeDisplayData, graphViewMode, graphData, activeSearchResultId, loadingNodes, debouncedSearchQuery, activeGraphDataset, searchResultData, selectedOntology }}
        runtime={{ gRef, zoomBehaviorRef, simulationRef, simulationLayoutRef, activeTooltipNodeRef, tooltipRef, highlightedNodeIdsRef, expandedNodesRef, nodeExpansionsRef, tickFrameRef, lastCenteredSearchRef, userInteractedWithGraphRef }}
        actions={{ onInspectNode: setInvestigationNodeId, hideAllTooltips, handleZoom, initializeNodePositions, processLinksForOffset, boundaryForce, calculateCurvedPath, tooltipCloseBtn, getCurrentGraphSlice, applyTooltipCloseHandler, wireTooltipRecButtons, openTooltipRecommendation, repositionTooltip, getRelationshipLabelColor, dragstarted, dragged, dragended, getNodeColor, getPrimaryNodeLabel, getNodeLabelColor, canCollapseNode, hasExpandableConnections, collapseNode, expandNode, buildRecActionBar }}
      />}

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
      <GraphInspector recPanel={recPanel} setRecPanel={setRecPanel} setActiveTab={setActiveTab} />

    </div>
  );
}

export default React.memo(GraphWorkspace);
