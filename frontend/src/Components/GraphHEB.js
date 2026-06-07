import React, { useEffect, useRef, useState, useCallback, useMemo, startTransition } from 'react';
import * as d3 from 'd3';
import '../CSS/GraphHEB.css';
import { useSchema } from '../SchemaContext';
import { useOntologies } from '../contexts/OntologyContext';
import { logger } from '../utils/logger';
import { safeGet, safeString } from '../utils/safeAccess';
import { buildUrl, replaceParams, API } from '../config';
import { apiClient } from '../services/apiClient';
import { buildTooltipHeader } from './tooltipBuilder';

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
const DISPLAY_NAME_PROPERTY = ['name', 'title', 'code', 'key', 'abbreviation'];
// const DISPLAY_NAME_PROPERTY = ['title', 'name'];
// const DISPLAY_NAME_PROPERTY = [];                // ← Neo4j label only
//
// DISPLAY_MODE  — controls what is shown in the node label.
//   'both-label-first'  → "Label - PropertyValue"   (default)
//   'both-prop-first'   → "PropertyValue (Label)"
//   'label-only'        → "Label"
//   'property-only'     → "PropertyValue"
const DISPLAY_MODE = 'property-only';
// const DISPLAY_MODE = 'both-prop-first';
// const DISPLAY_MODE = 'label-only';
// const DISPLAY_MODE = 'property-only';
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
const LINK_COLOR = '#4A90E2';        // ✅ Blue - visible on both light & dark backgrounds
const LINK_OPACITY = 0.8;            // ✅ Increased from 0.6 for better visibility
const LINK_STROKE_WIDTH = 3;         // ✅ Increased from 2 for clarity
const NODE_RADIUS = 14;
const LINK_DISTANCE = 100;
const CHARGE_STRENGTH = -150;        // ✅ Reduced from -300 to prevent node separation
const COLLIDE_RADIUS = 40;           // ✅ Reduced from 60 to allow denser graph
const ALPHA_TARGET_DRAG = 0.3;
const ALPHA_TARGET_END = 0;

// NEW CONSTANTS FOR CENTERING AND VIEWPORT
const CENTER_FORCE_STRENGTH = 0.05;
const VIEWPORT_PADDING = 50;

// NEW CONSTANTS FOR EXPAND/COLLAPSE
const EXPAND_SYMBOL_SIZE = 8;
const EXPAND_CIRCLE_RADIUS = 10;
 
// NEW CONSTANTS FOR ARROWHEADS
const ARROW_HEAD_LENGTH = 8;
const ARROW_HEAD_WIDTH = 4;
const ARROW_REF_X = NODE_RADIUS + 3; // Adjust so arrow starts slightly after node boundary

const CHAR_TIMES      = '\u00D7';     // ×   multiplication sign (close button)
const CHAR_MINUS      = '\u2212';     // −   minus sign
const CHAR_BULLET     = '\u2022';     // •   bullet
const CHAR_CHECK      = '\u2713';     // ✓   check mark
const CHAR_CROSS      = '\u2717';     // ✗   ballot x
// ───────────────────────────────────────────────────────────────────────────

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
  return (nodes, searchTerm) => {
    if (!searchTerm || searchTerm.length < 2) return nodes;
    
    const lowerSearchTerm = searchTerm.toLowerCase();
    return nodes.filter(node => {
      // Primary search fields (faster check first)
      if (node.name?.toLowerCase().includes(lowerSearchTerm)) return true;
      if (node.label?.toLowerCase().includes(lowerSearchTerm)) return true;
      
      // Label array search
      if (node.labels?.some(label => label.toLowerCase().includes(lowerSearchTerm))) return true;
      
      // Properties search (more expensive, check last)
      if (node.properties) {
        const propValues = Object.values(node.properties);
        return propValues.some(val => 
          typeof val === 'string' && val.toLowerCase().includes(lowerSearchTerm)
        );
      }
      
      return false;
    });
  };
};
 
const GraphHEB = ({ setData, setSearchResults, showChat, toggleChat, setActiveTab, setVisibleRelationships, chatResults }) => {
  const svgRef = useRef();
  const tooltipRef = useRef();
  const [tooltipDocked, setTooltipDocked] = useState(true);
  const tooltipDockedRef = useRef(tooltipDocked);
  useEffect(() => { tooltipDockedRef.current = tooltipDocked; }, [tooltipDocked]);
 
  const simulationRef = useRef(null);
  const gRef = useRef(null); // Ref for the main D3 group element
  const activeTooltipNodeRef = useRef(null); // Track which node/link the tooltip is showing for
  const timeoutsRef = useRef(new Set()); // Track active timeouts for cleanup

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
      tooltipEl.style.pointerEvents = 'none';
      activeTooltipNodeRef.current = null;
    });
  };

  // Helper: hide both tooltips
  const hideAllTooltips = () => {
    if (tooltipRef.current) { tooltipRef.current.style.opacity = '0'; tooltipRef.current.style.pointerEvents = 'none'; }
    activeTooltipNodeRef.current = null;
  };

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

  // Bridge: recommendation tooltip actions → slide-in panel
  React.useEffect(() => {
    window.__dt_rec_action = (service, nodeName) => {
      // Open the slide-in recommendation panel in graph view
      setRecPanel({ open: true, service, nodeName, loading: true, result: null, error: '' });
      hideAllTooltips();
      // Fire the API call
      const endpoint = service === 'change-impact'
        ? '/recommendations/change-impact'
        : service === 'similar-parts'
        ? '/recommendations/similar-parts'
        : '/recommendations/manufacturing';
      const body = service === 'change-impact'
        ? { change_name: nodeName }
        : service === 'similar-parts'
        ? { part_name: nodeName, top_n: 10 }
        : { part_name: nodeName };
      apiClient.post(buildUrl(endpoint), body)
        .then(resp => setRecPanel(prev => ({ ...prev, loading: false, result: resp.data })))
        .catch(err => setRecPanel(prev => ({ ...prev, loading: false, error: err.response?.data?.detail || err.message || 'Request failed' })));
    };
    return () => { delete window.__dt_rec_action; };
  }, []);

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
        const links = Array.from(rawLinks.values()).filter(l => nodeIds.has(l.source) && nodeIds.has(l.target));

        const labelSet = new Set();
        nodes.forEach(n => (n.labels || []).forEach(l => labelSet.add(l)));

        startTransition(() => {
          setSearchResultData({ nodes, links });
          setAvailableLabels(Array.from(labelSet).sort());
          setSelectedLabelFilter('ALL');
          setFilteredData({ nodes, links });
          if (setSearchResults) setSearchResults(nodes);
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
  const buildRecActionBar = (nodeName, nodeLabels) => {
    const escapedName = escapeHtml(nodeName || '');
    const btnStyle = 'display:inline-block;padding:4px 10px;border:none;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;margin-right:6px;color:#fff;';    return `
      <div style="padding:6px 8px 4px;margin-bottom:4px;border-bottom:1px solid #e2e6ea;display:flex;flex-wrap:wrap;gap:4px;">
        <button onclick="window.__dt_rec_action('change-impact','${escapedName}')" style="${btnStyle}background:#e74c3c;" title="Change Impact Analysis">Impact</button>
        <button onclick="window.__dt_rec_action('similar-parts','${escapedName}')" style="${btnStyle}background:#004B87;" title="Find Similar Parts">[FIND] Similar</button>
        <button onclick="window.__dt_rec_action('manufacturing','${escapedName}')" style="${btnStyle}background:#27ae60;" title="Manufacturing Processes">[MFG] Process</button>
      </div>`;
  };

  // Schema-driven display
  const { getDisplayName: schemaDisplayName, getDisplayLabel: schemaDisplayLabel } = useSchema() || {};

  // Performance: Optimize state management
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [filteredData, setFilteredData] = useState({ nodes: [], links: [] });
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  // Performance: Add loading states for better UX
  const [searchLoading, setSearchLoading] = useState(false);
  const [isLayoutSwitching, setIsLayoutSwitching] = useState(false);
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
  const [layoutType, setLayoutType] = useState('force-directed');
  const [prevLayoutType, setPrevLayoutType] = useState('force-directed');
  // Unified primary button color (match WhereUsedView request)

  // ── Recommendation: highlighted node names (set via "View in Graph") ──
  const [highlightedNodeNames, setHighlightedNodeNames] = useState(new Set());

  // ── Recommendation: slide-in panel state ──
  const [recPanel, setRecPanel] = useState({ open: false, service: null, nodeName: '', loading: false, result: null, error: '' });
  const primaryButtonColor = 'rgb(10, 130, 118)';

  useEffect(() => {
    const handleSchemaCleaned = () => {
      const empty = { nodes: [], links: [] };
      setGraphData(empty);
      setFilteredData(empty);
      setFullDataset(empty);
      setInitialData(empty);
      setSearchResultData(empty);
      setSearchQuery('');
      setSearchInput('');
      setAvailableLabels([]);
      setSelectedLabelFilter('ALL');
      setExpandedNodes(new Set());
      setLoadingNodes(new Set());
      setNodeExpansions(new Map());
      setTreeExpandedNodes(new Set());
      setSelectedOntology('ALL');
      selectedOntologyRef.current = 'ALL';
      setStepParts([]);
      setSelectedStepPart('ALL');
      setError(null);
      setData(empty);
    };
    window.addEventListener('dt-schema-cleaned', handleSchemaCleaned);
    return () => window.removeEventListener('dt-schema-cleaned', handleSchemaCleaned);
  }, [setData]);
  // New keyword-based dual-node comparison (graphfilter) states
  const [compareTermA, setCompareTermA] = useState('');
  const [compareTermB, setCompareTermB] = useState('');
  const [compareResultsA, setCompareResultsA] = useState([]); // results from /graphfilter for Node A
  const [compareResultsB, setCompareResultsB] = useState([]); // results from /graphfilter for Node B
  const [selectedCompareNodeA, setSelectedCompareNodeA] = useState(null);
  const [selectedCompareNodeB, setSelectedCompareNodeB] = useState(null);
  const [isCompareSearching, setIsCompareSearching] = useState({ A: false, B: false });
  const [propertyComparisonData, setPropertyComparisonData] = useState(null); // full property union diff
  // Label filter state: stores raw search results + available labels + user selection
  const [searchResultData, setSearchResultData] = useState({ nodes: [], links: [] });
  const [availableLabels, setAvailableLabels] = useState([]);
  const [selectedLabelFilter, setSelectedLabelFilter] = useState('ALL');
  // ── Graph View Mode: 'ontology' = Ontology Graph Visualization, 'individual' = Contextual Individual Graph View
  const [graphViewMode, setGraphViewMode] = useState('ontology');
  const graphViewModeRef = useRef('ontology');
  // Ontology viewer state
  const [selectedOntology, setSelectedOntology] = useState('ALL');
  const selectedOntologyRef = useRef('ALL');
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
  // Performance: Memoized search function
  const nodeSearchFunction = useMemo(() => createNodeSearchFunction(), []);
  
  // Comparative search API function
  // eslint-disable-next-line no-unused-vars
  const performComparativeSearch = useCallback(async (nodeType, name, version) => {
    try {
      const response = await apiClient.post(API.graph.comparativeSearch, {
        nodeType: nodeType.trim(),
        name: name.trim(),
        version: version.trim()
      });
      
      if (response.data?.results?.length > 0) {
        // Process the results similar to regular search
        const nodesMap = new Map();
        const rawLinks = new Map();
        
        response.data.results.forEach(record => {
          const n = record['n'];
          const r = record['r'];
          const m = record['m'];
          
          if (n) {
            const nodeIdN = n.elementId;
            const nodeN = {
              ...n.properties,
              elementId: nodeIdN,
              labels: n.labels || ['Node'],
              label: n.labels?.[0] || 'Node',
            };
            if (!nodesMap.has(nodeIdN)) {
              nodesMap.set(nodeIdN, nodeN);
            }
          }
          
          if (r && m) {
            const nodeIdM = m.elementId;
            if (!nodesMap.has(nodeIdM)) {
              nodesMap.set(nodeIdM, {
                ...m.properties,
                elementId: nodeIdM,
                labels: m.labels || ['Node'],
                label: m.labels?.[0] || 'Node',
              });
            }
            
            const linkId = r.elementId;
            if (!rawLinks.has(linkId)) {
              rawLinks.set(linkId, {
                elementId: linkId,
                source: r.start,
                target: r.end,
                type: r.type,
                properties: r.properties,
              });
            }
          }
        });
        
        const nodes = Array.from(nodesMap.values());
        const links = Array.from(rawLinks.values());
        
        return { nodes, links };
      }
      
      return { nodes: [], links: [] };
    } catch (error) {
      logger.error('Comparative search error:', error);
      throw error;
    }
  }, []);
  
  // Performance: Memoized color mapping - GENERIC VERSION
  const getNodeColor = useCallback((label) => {
    if (!label) return '#808080'; // Gray fallback for undefined labels

    // Explicit color map for known ontology labels - optimized for clarity
    const colorMap = {
      // Ontology Schema Layer (Classes and Properties)
      'OntologyClass':     '#003D82', // Deep blue - ontology classes
      'Class':             '#0056B3', // Standard blue - classes
      'ObjectProperty':    '#E67E22', // Orange - object properties (relationships)
      'DatatypeProperty':  '#F39C12', // Gold - datatype properties
      'OntologyProperty':  '#E67E22', // Orange - generic ontology properties
      'Property':          '#E67E22', // Orange - properties
      'Relationship':      '#27AE60', // Green - relationships
      'Annotation':        '#C0392B', // Dark red - annotations
      
      // Instance Data Layer
      'Individual':        '#27AE60', // Green - individual instances
      'Resource':          '#16A085', // Teal - resources
      'Datum':             '#16A085', // Teal - data
      
      // CAD/PLM Specific
      'Part':              '#2E8B57', // Sea green - parts
      'SurfaceFinish':     '#9B59B6', // Purple - surface finishes
      'Dimension':         '#2980B9', // Lighter blue - dimensions
      'GeometricTolerance':'#34495E', // Dark slate - tolerances
      
      // File Types
      'PLMXMLFile':        '#D35400', // Pumpkin - PLMXML files
      'StepFile':          '#7F8C8D', // Slate - STEP files
      'StepInstance':      '#34495E', // Dark slate - STEP instances
    };

    if (colorMap[label]) return colorMap[label];

    // Fallback: hash-based color for unknown labels
    const hash = label.split('').reduce((a, b) => {
      a = ((a << 5) - a) + b.charCodeAt(0);
      return a & a;
    }, 0);
    const hue = Math.abs(hash) % 360;
    return `hsl(${hue}, 70%, 50%)`;
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
      const rawSource = typeof link.source === 'object' ? (link.source.elementId || link.source.id || link.source.identity) : link.source;
      const rawTarget = typeof link.target === 'object' ? (link.target.elementId || link.target.id || link.target.identity) : link.target;
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
    
    // Find potential root nodes - handle expanded datasets better
    let roots;
    
    if (expandedNodes.size > 0) {
      // When we have expanded nodes, first try to find the originally expanded nodes as roots
      const expandedNodeIds = Array.from(expandedNodes);
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
          const rawSource = typeof link.source === 'object' ? (link.source.elementId || link.source.id || link.source.identity) : link.source;
          const rawTarget = typeof link.target === 'object' ? (link.target.elementId || link.target.id || link.target.identity) : link.target;
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
          const rawSource = typeof link.source === 'object' ? (link.source.elementId || link.source.id || link.source.identity) : link.source;
          const rawTarget = typeof link.target === 'object' ? (link.target.elementId || link.target.id || link.target.identity) : link.target;
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
    
    // For expansions, reorganize hierarchy to ensure proper parent-child relationships without duplicates
    if (expandedNodes.size > 0 && hierarchy.length > 0) {
      logger.render(`[Hierarchy] Reorganizing ${hierarchy.length} trees for ${expandedNodes.size} expanded nodes`);
      
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
      
      expandedNodes.forEach(expandedNodeId => {
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

  // Function to compare two node hierarchies and find differences
  // eslint-disable-next-line no-unused-vars
  const compareNodeHierarchies = useCallback((leftData, rightData) => {
    if (!leftData?.nodes?.length || !rightData?.nodes?.length) {
      return null;
    }
    
    // Create hierarchies for both sides
    const leftHierarchy = createHierarchicalData(leftData.nodes, leftData.links);
    const rightHierarchy = createHierarchicalData(rightData.nodes, rightData.links);
    
    // Find root nodes (main comparison targets)
    const leftRoot = leftHierarchy[0];
    const rightRoot = rightHierarchy[0];
    
    if (!leftRoot || !rightRoot) {
      return null;
    }
    
    // Compare function for nodes
    const compareNodes = (leftNode, rightNode) => {
      const differences = {};
      const leftProps = leftNode.properties || leftNode;
      const rightProps = rightNode.properties || rightNode;
      
      // Get all unique property keys
      const allKeys = new Set([...Object.keys(leftProps), ...Object.keys(rightProps)]);
      
      allKeys.forEach(key => {
        const leftVal = leftProps[key];
        const rightVal = rightProps[key];
        
        if (leftVal !== rightVal) {
          differences[key] = {
            left: leftVal || 'N/A',
            right: rightVal || 'N/A',
            status: leftVal && rightVal ? 'different' : (leftVal ? 'left_only' : 'right_only')
          };
        }
      });
      
      return differences;
    };
    
    // Compare children function
    const compareChildren = (leftChildren = [], rightChildren = []) => {
      const leftMap = new Map(leftChildren.map(child => [child.name || child.elementId, child]));
      const rightMap = new Map(rightChildren.map(child => [child.name || child.elementId, child]));
      
      const childComparisons = [];
      const allChildKeys = new Set([...leftMap.keys(), ...rightMap.keys()]);
      
      allChildKeys.forEach(key => {
        const leftChild = leftMap.get(key);
        const rightChild = rightMap.get(key);
        
        if (leftChild && rightChild) {
          // Both have this child - compare them
          const childDiffs = compareNodes(leftChild, rightChild);
          if (Object.keys(childDiffs).length > 0) {
            childComparisons.push({
              name: key,
              status: 'different',
              differences: childDiffs,
              leftChild,
              rightChild
            });
          }
        } else {
          // Only one side has this child
          childComparisons.push({
            name: key,
            status: leftChild ? 'left_only' : 'right_only',
            child: leftChild || rightChild
          });
        }
      });
      
      return childComparisons;
    };
    
    // Main comparison result
    const comparison = {
      rootDifferences: compareNodes(leftRoot, rightRoot),
      childrenComparison: compareChildren(leftRoot.children, rightRoot.children),
      leftHierarchy,
      rightHierarchy,
      leftRoot,
      rightRoot
    };
    
    return comparison;
  }, [createHierarchicalData]);

  // --- New: keyword search for comparison nodes using /graphfilter ---
  const performKeywordCompareSearch = useCallback(async (side, term) => {
    const trimmed = term.trim();
    if (!trimmed) return;
    setIsCompareSearching(prev => ({ ...prev, [side]: true }));
    try {
      const response = await apiClient.post(API.graph.graphfilter, { search: trimmed.toLowerCase() });
      const records = response.data?.results || [];
      const nodesMap = new Map();
      records.forEach(record => {
        const n = record['n'];
        const r = record['r'];
        const m = record['m'];
        if (n) {
          const nodeIdN = n.elementId;
          if (!nodesMap.has(nodeIdN)) {
            nodesMap.set(nodeIdN, {
              ...n.properties,
              elementId: nodeIdN,
              labels: n.labels || ['Node'],
              label: n.labels?.[0] || 'Node'
            });
          }
        }
        if (r && m) {
          const nodeIdM = m.elementId;
            if (!nodesMap.has(nodeIdM)) {
              nodesMap.set(nodeIdM, {
                ...m.properties,
                elementId: nodeIdM,
                labels: m.labels || ['Node'],
                label: m.labels?.[0] || 'Node'
              });
            }
        }
      });
      const list = Array.from(nodesMap.values());
      if (side === 'A') setCompareResultsA(list);
      else setCompareResultsB(list);
    } catch (e) {
      logger.error('Keyword comparison search failed', e);
      if (side === 'A') setCompareResultsA([]); else setCompareResultsB([]);
    } finally {
      setIsCompareSearching(prev => ({ ...prev, [side]: false }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const getNodeShortLabel = (n) => {
    if (!n) return 'Unknown';
    const firstLabel = n.labels?.[0] || n.label || 'Node';
    // Generic: try common name properties, fall back to label
    const name = n.name || n.properties?.name || n.title || n.properties?.title || firstLabel;
    return name;
  };

  // Render property comparison HTML for popup
  const renderPropertyComparisonHTML = (data) => {
    if (!data) return '<div>No comparison data.</div>';
    const { nodeA, nodeB, rows } = data;
    const esc = (v) => {
      if (v == null) return '';
      if (typeof v === 'object') return JSON.stringify(v);
      return String(v);
    };
    const rowHtml = rows.map(r => {
      const bgA = r.status === 'left_only' ? '#fff3cd' : r.status === 'different' ? '#f8f9fa' : '#ffffff';
      const bgB = r.status === 'right_only' ? '#ffe5d0' : r.status === 'different' ? '#f8f9fa' : '#ffffff';
      return `<tr>
        <td style='font-weight:${r.status!=='same'?'600':'400'};background:#f1f3f5;border-right:1px solid #eee;'>${r.property}</td>
        <td style='background:${bgA};font-family:monospace;'>${esc(r.left)}</td>
        <td style='background:${bgB};font-family:monospace;'>${esc(r.right)}</td>
        <td style='text-transform:capitalize;color:${r.status==='different'?'#d9534f':r.status==='same'?'#198754':'#343a40'};'>${r.status.replace('_',' ')}</td>
      </tr>`;
    }).join('');
    return `
      <html><head><title>Node Property Comparison</title>
      <style>
        body { font-family: Arial, sans-serif; background: #f8f9fa; margin: 0; padding: 24px; }
        h2 { color: #2C2C2C; }
        table { border-collapse: collapse; width: 100%; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
        th, td { padding: 8px 10px; border-bottom: 1px solid #eee; }
        th { background: #e9ecef; font-weight: bold; }
        tr:last-child td { border-bottom: none; }
        .export-btn { margin: 18px 0 0 0; padding: 8px 16px; background: #198754; color: #fff; border: none; border-radius: 4px; font-size: 14px; cursor: pointer; }
      </style>
      </head><body>
      <h2>Node Property Comparison</h2>
      <div style='margin-bottom:12px;'><b>Node A:</b> ${getNodeShortLabel(nodeA)}<br/><b>Node B:</b> ${getNodeShortLabel(nodeB)}</div>
      <table><thead><tr><th>Property</th><th>Node A</th><th>Node B</th><th>Status</th></tr></thead><tbody>
      ${rowHtml}
      </tbody></table>
      <button class='export-btn' onclick='window.exportCSV()'>Export CSV</button>
      <script>
        window.exportCSV = function() {
          const lines = [];
          lines.push(["Property","Node A","Node B","Status"].join(","));
          ${JSON.stringify(rows)}.forEach(r => {
            const esc = v => v==null?'':typeof v==="object"?JSON.stringify(v):String(v).replace(/"/g,'""');
            lines.push([r.property, esc(r.left), esc(r.right), r.status].join(","));
          });
          const blob = new Blob([lines.join("\n")], { type: 'text/csv;charset=utf-8;' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'node_comparison.csv';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        };
      </script>
      </body></html>
    `;
  };

  // Open popup and render property comparison
  const openComparisonPopup = useCallback(() => {
    if (!selectedCompareNodeA || !selectedCompareNodeB) return;
    const leftProps = { ...(selectedCompareNodeA.properties || {}), ...selectedCompareNodeA };
    const rightProps = { ...(selectedCompareNodeB.properties || {}), ...selectedCompareNodeB };
    delete leftProps.children; delete rightProps.children;
    const allKeys = new Set([...Object.keys(leftProps), ...Object.keys(rightProps)]);
    const rows = [];
    allKeys.forEach(k => {
      const l = leftProps[k];
      const r = rightProps[k];
      const same = l === r;
      rows.push({ property: k, left: l === undefined ? '' : l, right: r === undefined ? '' : r, status: l === undefined ? 'right_only' : r === undefined ? 'left_only' : (same ? 'same' : 'different') });
    });
    rows.sort((a,b)=> a.property.localeCompare(b.property));
    const data = { nodeA: selectedCompareNodeA, nodeB: selectedCompareNodeB, rows };
    const html = renderPropertyComparisonHTML(data);
    const popup = window.open('', '_blank', 'width=1100,height=800,scrollbars=yes,resizable=yes');
    if (popup) {
      popup.document.write(html);
      popup.document.close();
    } else {
      alert('Popup blocked! Please allow popups for this site.');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCompareNodeA, selectedCompareNodeB]);

  // Reset property comparison when selection changes
  useEffect(()=> { setPropertyComparisonData(null); }, [selectedCompareNodeA, selectedCompareNodeB]);
  

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
  if (!d) return 'Unknown';

  const props = d.properties || d;
  const nodeLabel = d.labels?.[0] || d.label || '';

  // Resolve property from priority list (see DISPLAY_NAME_PROPERTY at top of file)
  const propValue = resolveDisplayProp(props);

  // Schema-driven fallback
  if (!propValue && schemaDisplayName) return schemaDisplayName(d);

  // Heuristic fallback when configured property list yields nothing
  const displayValue = propValue ??
    (props.name ?? props.Name ?? props.PartName ?? props.CADDocumentName ?? props.ObjectType ??
     props.id ?? props.identifier ?? props.uuid ?? null);

  return formatNodeDisplay(nodeLabel, displayValue != null ? String(displayValue) : null);
}, [schemaDisplayName]);


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
    if (expandedNodes.size > 0 && data.links && data.links.length > 0) {
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
          d3.select(tooltipRef.current).style('z-index', 12).style('pointer-events', 'auto');
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
          tooltipContent += buildRecActionBar(d.name || props.name, d.labels);
          
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
        .attr('fill', d => getNodeColor((d.labels && d.labels.length > 0) ? d.labels[0] : 'Unknown'))
        .attr('stroke', '#fff')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .on('mouseover', function(event, d) {
          d3.select(this)
            .attr('stroke-width', 3);
        })
        .on('mouseout', function(event, d) {
          d3.select(this)
            .attr('stroke-width', 2);
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
          .attr('fill', d => getNodeColor((d.labels && d.labels.length > 0) ? d.labels[0] : 'Unknown'))
          .attr('fill-opacity', 0.15)
          .attr('stroke', d => getNodeColor((d.labels && d.labels.length > 0) ? d.labels[0] : 'Unknown'))
          .attr('stroke-width', 1.5)
          .attr('class', 'tree-node-badge');
          
        // Add badge text with proper centering
        row.append('text')
          .attr('x', d => 55 + d.level * indentWidth + badgeWidth / 2)
          .attr('y', rowHeight / 2 + 3)
          .attr('text-anchor', 'middle')
          .attr('font-size', '10px')
          .attr('font-weight', 'bold')
          .attr('fill', d => getNodeColor((d.labels && d.labels.length > 0) ? d.labels[0] : 'Unknown'))
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
          if (expandedNodes.has(d.elementId)) {
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
            .attr('stroke-width', 1.5);
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
            .attr('stroke-width', 2)
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
    if (layoutType === 'indented-tree' && expandedNodes.size > 0) {
      logger.render('[TreeLayout] Data changed with expanded nodes, updating tree state');
      
      // When data changes due to expansions, ensure the tree expanded state includes
      // all nodes that should be visible based on the new hierarchy
      const currentData = filteredData.nodes.length > 0 ? filteredData : fullDataset;
      if (currentData && currentData.nodes && currentData.links) {
        const newHierarchy = createHierarchicalData(currentData.nodes, currentData.links);
        
        // Auto-expand nodes that have children and are part of expansions
        const newTreeExpanded = new Set(treeExpandedNodes);
        
        const addExpandedChildren = (node) => {
          if (expandedNodes.has(node.elementId) && node.children && node.children.length > 0) {
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
        const sourceId = typeof link.source === 'object' ? link.source.elementId : link.source;
        const targetId = typeof link.target === 'object' ? link.target.elementId : link.target;
        const pairKey = [sourceId, targetId].sort().join('-');
        hasChildPairs.add(pairKey);
      }
    });
    
    // Second pass: filter out HAS_PARENT if HAS_CHILD exists for the same node pair
    links.forEach(link => {
      if (link.type === 'HAS_PARENT') {
        const sourceId = typeof link.source === 'object' ? link.source.elementId : link.source;
        const targetId = typeof link.target === 'object' ? link.target.elementId : link.target;
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
      const sourceId = typeof link.source === 'object' ? link.source.elementId : link.source;
      const targetId = typeof link.target === 'object' ? link.target.elementId : link.target;
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
    const sourceId = typeof link.source === 'object' ? link.source.elementId : link.source;
    const targetId = typeof link.target === 'object' ? link.target.elementId : link.target;
    
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

  // Performance: Optimized layout change handler with monitoring
  const handleLayoutChange = useCallback((newLayoutType) => {
    if (newLayoutType !== layoutType) {
      const startTime = performance.now();
      setIsLayoutSwitching(true);
      
      logger.render(`[SYNC] Layout switching from ${layoutType} to ${newLayoutType}`);
      
      // Stop current simulation immediately for smooth transition
      if (simulationRef.current && newLayoutType === 'indented-tree') {
        simulationRef.current.stop();
        simulationRef.current = null;
      }
      
      setLayoutType(newLayoutType);
      
      // Ensure we have the full dataset available for both layouts
      if (newLayoutType === 'force-directed') {
        // For graph layout, use full dataset
        logger.render(`[RENDER] Restoring full dataset for graph layout: ${graphData.nodes?.length || 0} nodes`);
        setFilteredData({
          nodes: [...(graphData.nodes || [])],
          links: [...(graphData.links || [])]
        });
      } else if (newLayoutType === 'indented-tree') {
        // For tree layout, use current filteredData but ensure tree expansion is initialized
        try {
          const currentNodes = filteredData.nodes?.length > 0 ? filteredData.nodes : graphData.nodes || [];
          const currentLinks = filteredData.links?.length > 0 ? filteredData.links : graphData.links || [];
          const roots = createHierarchicalData(currentNodes, currentLinks);
          const rootIds = roots.map(r => r.elementId).filter(Boolean);
          setTreeExpandedNodes(new Set(rootIds));
          logger.render(`[TREE] Tree layout initialized with ${currentNodes.length} nodes, ${rootIds.length} roots`);
        } catch (e) {
          logger.warn('Tree expansion init failed', e);
        }
      }
      
      // Performance monitoring
      requestAnimationFrame(() => {
        const endTime = performance.now();
        logger.render(`[PERF] Layout switch completed in ${(endTime - startTime).toFixed(2)}ms`);
        setIsLayoutSwitching(false);
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutType, graphData, createHierarchicalData]);

  // Throttled simulation tick to improve performance
  // eslint-disable-next-line no-unused-vars
  const throttledTick = useCallback(() => {
    let lastTickTime = 0;
    return function() {
      const now = Date.now();
      if (now - lastTickTime > 16) { // ~60fps limit
        lastTickTime = now;
        return true;
      }
      return false;
    };
  }, []);

  // Performance: Optimized data fetching with caching and error handling
  useEffect(() => {
    const fetchData = async () => {
      performanceLog('[SYNC] Starting data fetch from API...');
      setIsLoading(true);
      setError(null);
      
      try {
        performanceLog('[API] Making API call to /graphvis...');
        const response = await apiClient.get(API.graph.graphvis);
        performanceLog('[DATA] API Response received:', {
          status: response.status,
          dataExists: !!response.data,
          resultsCount: response.data?.results?.length || 0,
          firstResult: response.data?.results?.[0]
        });
        
        // Process initial data directly
        if (response.data?.results?.length > 0) {
          logger.render('[SEARCH] Processing API data...');
          const nodesMap = new Map();
          const rawLinks = new Map();
          
          response.data.results.forEach(record => {
            const n = record['n'];
            const r = record['r'];
            const m = record['m'];
            
            if (n) {
              const nodeIdN = n.elementId;
              const nodeN = {
                ...n.properties,
                elementId: nodeIdN,
                labels: n.labels || ['Node'],
                label: n.labels?.[0] || 'Node',
              };
              if (!nodesMap.has(nodeIdN)) {
                nodesMap.set(nodeIdN, nodeN);
              }
            }
            
            if (r && m) {
              const nodeIdM = m.elementId;
              if (!nodesMap.has(nodeIdM)) {
                nodesMap.set(nodeIdM, {
                  ...m.properties,
                  elementId: nodeIdM,
                  labels: m.labels || ['Node'],
                  label: m.labels?.[0] || 'Node',
                });
              }
              
              const linkId = r.elementId;
              if (!rawLinks.has(linkId)) {
                rawLinks.set(linkId, {
                  elementId: linkId,
                  source: r.start,
                  target: r.end,
                  type: r.type,
                  properties: r.properties,
                });
              }
            }
          });
          
          const nodes = Array.from(nodesMap.values());
          const finalLinks = Array.from(rawLinks.values());
          const existingNodeIds = new Set(nodes.map(node => node.elementId));
          const validatedLinks = finalLinks.filter(link => 
            existingNodeIds.has(link.source) && existingNodeIds.has(link.target)
          );
          
          logger.render(`[OK] Data processed successfully: ${nodes.length} nodes, ${validatedLinks.length} links`);
          
          // Batch all data state updates for better performance
          startTransition(() => {
            const dataSet = { nodes, links: validatedLinks };
            setData(dataSet);
            setGraphData(dataSet);
            setFilteredData(dataSet);
            setFullDataset(dataSet);
            setInitialData(dataSet);
          });
        } else {
          logger.render('[WARN] No results in API response or empty results array');
        }
        
        setIsLoading(false);
      } catch (err) {
        logger.error('[ERROR] Data Fetch Error:', err);
        logger.error('Error details:', {
          message: err.message,
          response: err.response?.data,
          status: err.response?.status
        });
        setError(`Failed to load graph data: ${err.message}`);
        setIsLoading(false);
      }
    
 };

  fetchData();
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

        if (connected && previousConnected === false && graphData.nodes.length === 0) {
          // Connection was restored but graph is empty - trigger refresh
          logger.data('Neo4j reconnected, refreshing graph...');
          const graphResponse = await apiClient.get(API.graph.graphvis);
          if (graphResponse.data?.results?.length > 0) {
            // Process and update graph
            const nodesMap = new Map();
            const rawLinks = new Map();
            
            graphResponse.data.results.forEach(record => {
              const n = record['n'];
              const r = record['r'];
              const m = record['m'];
              
              if (n) {
                const nodeIdN = n.elementId;
                if (!nodesMap.has(nodeIdN)) {
                  nodesMap.set(nodeIdN, {
                    ...n.properties,
                    elementId: nodeIdN,
                    labels: n.labels || ['Node'],
                    label: n.labels?.[0] || 'Node',
                  });
                }
              }
              
              if (r && m) {
                const nodeIdM = m.elementId;
                if (!nodesMap.has(nodeIdM)) {
                  nodesMap.set(nodeIdM, {
                    ...m.properties,
                    elementId: nodeIdM,
                    labels: m.labels || ['Node'],
                    label: m.labels?.[0] || 'Node',
                  });
                }
                
                const linkId = r.elementId;
                if (!rawLinks.has(linkId)) {
                  rawLinks.set(linkId, {
                    elementId: linkId,
                    source: r.start,
                    target: r.end,
                    type: r.type,
                    properties: r.properties,
                  });
                }
              }
            });
            
            const nodes = Array.from(nodesMap.values());
            const finalLinks = Array.from(rawLinks.values());
            const existingNodeIds = new Set(nodes.map(node => node.elementId));
            const validatedLinks = finalLinks.filter(link => 
              existingNodeIds.has(link.source) && existingNodeIds.has(link.target)
            );
            
            startTransition(() => {
              const dataSet = { nodes, links: validatedLinks };
              setData(dataSet);
              setGraphData(dataSet);
              setFilteredData(dataSet);
              setFullDataset(dataSet);
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
  }, [graphData.nodes.length, setData]);

 
  // Performance: Optimized search with debouncing and caching
  useEffect(() => {
    if (!debouncedSearchQuery) {
      // Only reset if no nodes are currently expanded
      if (expandedNodes.size === 0) {
        // Reset to current data when search is cleared
        // Use filteredData if it has more nodes than graphData (indicating expanded state)
        const currentData = filteredData.nodes.length > graphData.nodes.length ? filteredData : graphData;
        setFilteredData(currentData);
        // Reset search results for other components
        if (setSearchResults) {
          setSearchResults(currentData.nodes);
        }
      }
      setSearchLoading(false);
      return;
    }

    // Cancel previous in-flight search request to prevent race conditions
    const abortController = new AbortController();

    const performSearch = async () => {
      performanceLog('[SEARCH] Starting search for:', debouncedSearchQuery);
      setSearchLoading(true);
      
      try {
        const response = await apiClient.post(API.graph.graphfilter, {
          search: debouncedSearchQuery.toLowerCase()
        }, { signal: abortController.signal });
        
        performanceLog('[SEARCH] Search API response:', response.data?.results?.length || 0, 'results');
        if (response.data?.results?.length > 0) {
          logger.render('[SEARCH] First result structure:', JSON.stringify(response.data.results[0], null, 2));
        }
        
        // Process search results directly without setting intermediate result state
        if (response.data?.results?.length > 0) {
          const nodesMap = new Map();
          const rawLinks = new Map();
          
          response.data.results.forEach(record => {
            const n = record['n'];
            const r = record['r'];
            const m = record['m'];
            
            if (n) {
              const nodeIdN = n.elementId;
              const nodeN = {
                ...n.properties,
                elementId: nodeIdN,
                labels: n.labels || ['Node'],
                label: n.labels?.[0] || 'Node',
              };
              if (!nodesMap.has(nodeIdN)) {
                nodesMap.set(nodeIdN, nodeN);
              }
            }
            
            if (r && m) {
              const nodeIdM = m.elementId;
              if (!nodesMap.has(nodeIdM)) {
                nodesMap.set(nodeIdM, {
                  ...m.properties,
                  elementId: nodeIdM,
                  labels: m.labels || ['Node'],
                  label: m.labels?.[0] || 'Node',
                });
              }
              
              const linkId = r.elementId;
              if (!rawLinks.has(linkId)) {
                rawLinks.set(linkId, {
                  elementId: linkId,
                  source: r.start,
                  target: r.end,
                  type: r.type,
                  properties: r.properties,
                });
              }
            }
          });
          
          const nodes = Array.from(nodesMap.values());
          const links = Array.from(rawLinks.values());
          
          // Validate links
          const existingNodeIds = new Set(nodes.map(node => node.elementId));
          const validatedLinks = links.filter(link => 
            existingNodeIds.has(link.source) && existingNodeIds.has(link.target)
          );
          
          logger.render('[SEARCH] Search processed:', nodes.length, 'nodes,', validatedLinks.length, 'links');
          
          // For search results, REPLACE existing data instead of merging
          // This prevents contamination from previous searches or expansions
          let finalNodes = nodes;
          let finalLinks = validatedLinks;
          
          // Only preserve expansion data if the expanded nodes are part of current search results
          if (expandedNodes.size > 0) {
            logger.render('[SEARCH] Checking expanded nodes for relevance to current search');
            const searchNodeIds = new Set(nodes.map(n => n.elementId));
            const relevantExpansions = new Set();
            
            // Only keep expansions where the original expanded node is in current search
            for (const expandedNodeId of expandedNodes) {
              if (searchNodeIds.has(expandedNodeId)) {
                relevantExpansions.add(expandedNodeId);
                logger.render('[SEARCH] Keeping expansion for:', expandedNodeId);
              } else {
                logger.render('[SEARCH] Removing irrelevant expansion for:', expandedNodeId);
              }
            }
            
            // Batch expansion tracking updates
            startTransition(() => {
              setExpandedNodes(relevantExpansions);
              const updatedNodeExpansions = new Map();
              for (const nodeId of relevantExpansions) {
                if (nodeExpansions.has(nodeId)) {
                  updatedNodeExpansions.set(nodeId, nodeExpansions.get(nodeId));
                }
              }
              setNodeExpansions(updatedNodeExpansions);
            });
          }
          
          // Batch search result updates for better performance
          startTransition(() => {
            // Store raw search results for label filtering
            setSearchResultData({ nodes: finalNodes, links: finalLinks });
            // Extract unique labels from search results
            const labelSet = new Set();
            finalNodes.forEach(n => {
              (n.labels || []).forEach(l => labelSet.add(l));
            });
            const sortedLabels = Array.from(labelSet).sort();
            setAvailableLabels(sortedLabels);
            setSelectedLabelFilter('ALL');
            // Set filteredData (unfiltered initially)
            setFilteredData({ nodes: finalNodes, links: finalLinks });

            // Update search results for other components
            if (setSearchResults) {
              setSearchResults(finalNodes);
            }
          });
        } else {
          // Batch no results updates
          startTransition(() => {
            setFilteredData({ nodes: [], links: [] });
            // Update search results to empty array for other components
            if (setSearchResults) {
              setSearchResults([]);
            }
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
        // Fallback to client-side search if server search fails
        // Use fullDataset to include expanded nodes in search
        const searchData = fullDataset.nodes.length > 0 ? fullDataset : graphData;
        const filteredNodes = nodeSearchFunction(searchData.nodes, debouncedSearchQuery);
        const filteredNodeIds = new Set(filteredNodes.map(n => n.elementId));
        const filteredLinks = searchData.links.filter(
          l => filteredNodeIds.has(l.source?.elementId || l.source) && 
               filteredNodeIds.has(l.target?.elementId || l.target)
        );
        // Batch fallback search updates
        startTransition(() => {
          setFilteredData({ nodes: filteredNodes, links: filteredLinks });
          // Update search results for other components  
          if (setSearchResults) {
            setSearchResults(filteredNodes);
          }
          setSearchLoading(false);
        });
      }
    };

    performSearch();
    // Cleanup: abort in-flight request when query changes or component unmounts
    return () => abortController.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearchQuery, nodeSearchFunction]);

  // Label filter effect: when user picks a label from dropdown, filter the search results
  useEffect(() => {
    if (!debouncedSearchQuery || searchResultData.nodes.length === 0) return;
    if (selectedLabelFilter === 'ALL') {
      // Show everything from the search results
      setFilteredData(searchResultData);
      if (setSearchResults) setSearchResults(searchResultData.nodes);
    } else {
      // Filter nodes that have the selected label
      const filtered = searchResultData.nodes.filter(n =>
        (n.labels || []).includes(selectedLabelFilter)
      );
      const filteredIds = new Set(filtered.map(n => n.elementId));
      const filteredLinks = searchResultData.links.filter(l =>
        filteredIds.has(l.source?.elementId || l.source) &&
        filteredIds.has(l.target?.elementId || l.target)
      );
      setFilteredData({ nodes: filtered, links: filteredLinks });
      if (setSearchResults) setSearchResults(filtered);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLabelFilter, searchResultData]);

  // ── Ontology viewer: fetch ontology graph when dropdown changes ─────────
  const fetchOntologyGraph = useCallback(async (ontologyType, partName) => {
    if (ontologyType === 'ALL') {
      // Reset to initial full graph
      setOntologyGraphMessage('');
      setFilteredData(initialData);
      setGraphData(initialData);
      setFullDataset(initialData);
      setData(initialData);
      if (setSearchResults) setSearchResults(initialData.nodes);
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
        response = await apiClient.getOntologyInstances(base, { include_rels: true, limit: 1000 });
      } else if (ontologyType === 'mbse_instances') {
        response = await apiClient.get(API.graph.ontologyMbseInstances);
      } else {
        const endpointPath = replaceParams(API.graph.graphvisByOntology, { prefix: ontologyType });
        response = await apiClient.get(endpointPath);
      }
      if (response.data?.results?.length > 0) {
        const nodesMap = new Map();
        const rawLinks = new Map();

        response.data.results.forEach(record => {
          const n = record['n'];
          const r = record['r'];
          const m = record['m'];

          if (n) {
            const nodeIdN = n.elementId;
            if (!nodesMap.has(nodeIdN)) {
              nodesMap.set(nodeIdN, {
                ...n.properties,
                elementId: nodeIdN,
                labels: n.labels || ['Node'],
                label: n.labels?.[0] || 'Node',
              });
            }
          }

          if (r && m) {
            const nodeIdM = m.elementId;
            if (!nodesMap.has(nodeIdM)) {
              nodesMap.set(nodeIdM, {
                ...m.properties,
                elementId: nodeIdM,
                labels: m.labels || ['Node'],
                label: m.labels?.[0] || 'Node',
              });
            }
            const linkId = r.elementId;
            if (!rawLinks.has(linkId)) {
              rawLinks.set(linkId, {
                elementId: linkId,
                source: r.start,
                target: r.end,
                type: r.type,
                properties: r.properties,
              });
            }
          }
        });

        const nodes = Array.from(nodesMap.values());
        const existingNodeIds = new Set(nodes.map(node => node.elementId));
        
        const sampleLinks = Array.from(rawLinks.values()).slice(0, 2);
        logger.ontology('[ONTOLOGY] Graph payload sample', {
          nodes: nodes.slice(0, 2).map(n => ({ elementId: n.elementId, label: n.label })),
          nodeCount: nodes.length,
          rawLinkCount: rawLinks.size,
          links: sampleLinks.map(l => ({
          source: l.source, 
          target: l.target,
          sourceExists: existingNodeIds.has(l.source),
          targetExists: existingNodeIds.has(l.target)
          })),
        });
        
        const validatedLinks = Array.from(rawLinks.values()).filter(link =>
          existingNodeIds.has(link.source) && existingNodeIds.has(link.target)
        );
        
        logger.ontology('[ONTOLOGY] Validated graph links', validatedLinks.length);
        if (nodes.length > 0 && rawLinks.size > 0 && validatedLinks.length === 0) {
          setOntologyGraphMessage('Ontology has relationships, but visualization could not match relationship source/target IDs.');
        } else if (nodes.length > 0 && validatedLinks.length === 0) {
          setOntologyGraphMessage('Ontology has classes but no relationships.');
        } else {
          setOntologyGraphMessage('');
        }

        const dataSet = { nodes, links: validatedLinks };
        setFilteredData(dataSet);
        setGraphData(dataSet);
        setFullDataset(dataSet);
        setData(dataSet);
        if (setSearchResults) setSearchResults(nodes);
        logger.render(`[ONTOLOGY] Loaded ${ontologyType}: ${nodes.length} nodes, ${validatedLinks.length} links`);
      } else {
        const empty = { nodes: [], links: [] };
        setOntologyGraphMessage(response.data?.message || response.data?.error || 'Neo4j query returned zero records.');
        setFilteredData(empty);
        setGraphData(empty);
        setFullDataset(empty);
        setData(empty);
        if (setSearchResults) setSearchResults([]);
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

  // Build dataset for Contextual Individual Graph View from the latest graph snapshot
  const buildIndividualViewDataset = useCallback((sourceData) => {
    const nodes = sourceData?.nodes || [];
    const links = sourceData?.links || [];

    // Filter out ONLY ontology/schema nodes - keep everything else (all instance data)
    const indNodes = nodes.filter(n => {
      const labels = n.labels || [];
      // Exclude pure ontology/schema nodes
      if (labels.includes('OntologyClass') || labels.includes('ObjectProperty') || labels.includes('DatatypeProperty')) {
        return false;
      }
      // Include everything else (all instance nodes, data, etc.)
      return true;
    });

    const indIds = new Set(indNodes.map(n => n.elementId));
    // After D3 simulation runs, link.source/target are mutated to node objects — handle both
    const getLinkEndId = (endpoint) =>
      typeof endpoint === 'object' ? (endpoint?.elementId || endpoint?.id) : endpoint;

    // Include all links where at least one endpoint is an individual/instance node
    const indLinks = links.filter(l => {
      const srcId = getLinkEndId(l.source);
      const tgtId = getLinkEndId(l.target);
      return indIds.has(srcId) || indIds.has(tgtId);
    });

    // Also bring in neighbor nodes referenced by those links so the connected graph is visible
    const referencedNodeIds = new Set();
    indLinks.forEach(l => {
      referencedNodeIds.add(getLinkEndId(l.source));
      referencedNodeIds.add(getLinkEndId(l.target));
    });

    const allNodeIds = new Set([...indIds, ...referencedNodeIds]);
    const allNodes = nodes.filter(n => allNodeIds.has(n.elementId));

    return { nodes: allNodes, links: indLinks };
  }, []);

  // When graph view mode switches, load the appropriate dataset
  useEffect(() => {
    graphViewModeRef.current = graphViewMode;
    setSearchQuery('');
    setSearchInput('');
    setSelectedLabelFilter('ALL');
    setAvailableLabels([]);
    setSearchResultData({ nodes: [], links: [] });
    setExpandedNodes(new Set());
    setNodeExpansions(new Map());

    if (graphViewMode === 'individual') {
      const dataSet = buildIndividualViewDataset(initialData);
      startTransition(() => {
        setFilteredData(dataSet);
        setGraphData(dataSet);
        setFullDataset(dataSet);
        setData(dataSet);
      });
      // Defer parent setState — must NOT be called inside a state updater or during render
      if (setSearchResults) setTimeout(() => setSearchResults(dataSet.nodes), 0);
    } else {
      // Ontology mode — restore or refetch based on active ontology selection.
      const selected = selectedOntologyRef.current || 'ALL';
      if (selected === 'ALL') {
        // Already on ALL — selectedOntology effect won't re-fire, so restore manually.
        startTransition(() => {
          setFilteredData(initialData);
          setGraphData(initialData);
          setFullDataset(initialData);
          setData(initialData);
        });
        if (setSearchResults) setTimeout(() => setSearchResults(initialData.nodes), 0);
      } else {
        // Force refresh since selectedOntology effect does not run on graphViewMode changes.
        const part = selected === 'step' ? selectedStepPart : 'ALL';
        fetchOntologyGraph(selected, part);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphViewMode, buildIndividualViewDataset]);

  // Keep Individual view in sync when fresh initial graph data arrives.
  useEffect(() => {
    if (graphViewModeRef.current !== 'individual') return;
    const dataSet = buildIndividualViewDataset(initialData);
    startTransition(() => {
      setFilteredData(dataSet);
      setGraphData(dataSet);
      setFullDataset(dataSet);
      setData(dataSet);
    });
    if (setSearchResults) setTimeout(() => setSearchResults(dataSet.nodes), 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialData, buildIndividualViewDataset]);

  // When ontology selection changes, fetch graph and optionally fetch STEP parts
  useEffect(() => {
    if (graphViewModeRef.current === 'individual') return; // individual mode manages its own data
    // Clear search state when switching ontology
    setSearchQuery('');
    setSearchInput('');
    setSelectedLabelFilter('ALL');
    setAvailableLabels([]);
    setSearchResultData({ nodes: [], links: [] });
    setExpandedNodes(new Set());
    setNodeExpansions(new Map());

    if (selectedOntology === 'step') {
      // Fetch STEP parts list for secondary filter
      setStepPartsLoading(true);
      setStepPartsError(null);
      apiClient.get(API.graph.stepParts)
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
  }, [selectedOntology, fetchOntologyGraph]);

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
    // Show expand option only in search context and the node is not already expanded
    const isNotExpanded = !expandedNodes.has(nodeData.elementId);
    const hasSearchQuery = !!debouncedSearchQuery;
    
    // Only show expand buttons in search context
    return hasSearchQuery && isNotExpanded;
  };

  // Function to determine if a node can be collapsed
  const canCollapseNode = (nodeData) => {
    // Show collapse option only for nodes that are currently expanded in search context
    const isExpanded = expandedNodes.has(nodeData.elementId);
    const hasSearchQuery = !!debouncedSearchQuery; // Use debouncedSearchQuery for consistency
    
    // Only show collapse buttons in search context
    return hasSearchQuery && isExpanded;
  };

  // Function to expand a node using graphtraverse API - ONE LEVEL ONLY expansion
  const expandNode = async (nodeId) => {
    if (expandedNodes.has(nodeId)) {
      return;
    }
    
    setLoadingNodes(prev => new Set([...prev, nodeId]));
    
    // Track nodes that will be added by this expansion
    const addedNodeIds = new Set();
    const addedLinkIds = new Set();
    
    try {
      const response = await apiClient.get(replaceParams(API.graph.graphtraverseNode, { node_id: nodeId }));
      
      if (response.data && response.data.results) {
        // Start with ONLY the current search results, not all filteredData
        const newNodesMap = new Map();
        const newLinksMap = new Map();
        
        // ONLY add nodes that are part of current search or already expanded
        if (debouncedSearchQuery) {
          // In search mode: only keep nodes that match current search
          // This prevents contamination from previous searches
          filteredData.nodes.forEach(node => {
            // Only add if it's the node being expanded or was added by a current expansion
            if (node.elementId === nodeId || expandedNodes.has(node.elementId)) {
              newNodesMap.set(node.elementId, node);
            }
          });
          
          filteredData.links.forEach(link => {
            // Only add links that connect to nodes we're keeping
            if (newNodesMap.has(link.source) && newNodesMap.has(link.target)) {
              newLinksMap.set(link.elementId, link);
            }
          });
        } else {
          // Not in search mode: add all existing nodes
          filteredData.nodes.forEach(node => {
            newNodesMap.set(node.elementId, node);
          });
          
          filteredData.links.forEach(link => {
            newLinksMap.set(link.elementId, link);
          });
        }
        
        // Process the API response - ADD ALL DIRECT CONNECTIONS
        response.data.results.forEach(record => {
          const n = record['n'];
          const r = record['r'];
          const m = record['m'];
          
          // Process relationships where either n or m is the node we're expanding
          if (r && ((n && n.elementId === nodeId) || (m && m.elementId === nodeId))) {
            // Add the relationship with consistent format
            const linkId = r.elementId;
            if (!newLinksMap.has(linkId)) {
              newLinksMap.set(linkId, {
                elementId: linkId,
                source: r.start, // Keep as raw ID for consistency
                target: r.end,   // Keep as raw ID for consistency
                type: r.type,
                properties: r.properties,
              });
              addedLinkIds.add(linkId);
            }
            
            // Add the connected node (either n or m, whichever is NOT the expanded node)
            const connectedNode = (n && n.elementId === nodeId) ? m : n;
            if (connectedNode) {
              const connectedNodeId = connectedNode.elementId;
              const newNode = {
                ...connectedNode.properties,
                elementId: connectedNodeId,
                labels: connectedNode.labels || ['Node'],
                label: connectedNode.labels[0] || 'Node',
              };
              if (!newNodesMap.has(connectedNodeId)) {
                newNodesMap.set(connectedNodeId, newNode);
                addedNodeIds.add(connectedNodeId);
                performanceLog('Added direct connection:', connectedNodeId);
              }
            }
          }
        });
        
        const finalNodes = Array.from(newNodesMap.values());
        const finalLinks = Array.from(newLinksMap.values());
        
        performanceLog('One-level expansion:', addedNodeIds.size, 'new nodes,', addedLinkIds.size, 'new links');
        
        // Validate links
        const existingNodeIds = new Set(finalNodes.map(node => node.elementId));
        const validatedLinks = finalLinks.filter(link => 
          existingNodeIds.has(link.source) && existingNodeIds.has(link.target)
        );
        
        // Batch all state updates for better performance
        startTransition(() => {
          // Update the current filtered data (what's currently displayed)
          setFilteredData({ nodes: finalNodes, links: validatedLinks });
          setData({ nodes: finalNodes, links: validatedLinks });

          // ONLY update fullDataset if we're NOT in a search state
          // This prevents reverting to default nodes when expanding during search
          if (!debouncedSearchQuery) {
            setFullDataset({ nodes: finalNodes, links: validatedLinks });
            setGraphData({ nodes: finalNodes, links: validatedLinks });
          }

          // Update search results if search is active
          if (setSearchResults && debouncedSearchQuery) {
            setSearchResults(finalNodes);
          }

          if (setVisibleRelationships) {
            setVisibleRelationships(validatedLinks);
          }

          // Store which nodes and links were added by this expansion
          setNodeExpansions(prev => {
            const newMap = new Map([...prev, [nodeId, { addedNodeIds, addedLinkIds, level: 1 }]]);
            return newMap;
          });

          setExpandedNodes(prev => {
            const newSet = new Set([...prev, nodeId]);
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
    logger.render('Current nodeExpansions:', Array.from(nodeExpansions.entries()));
    logger.render('Current expandedNodes:', Array.from(expandedNodes));
    logger.render('Current filteredData nodes:', filteredData.nodes.map(n => n.elementId));
    
    // Get the expansion info for this node
    const expansionInfo = nodeExpansions.get(nodeId);
    if (!expansionInfo) {
      logger.render('ERROR: No expansion info found for node:', nodeId);
      logger.render('Available expansions:', Array.from(nodeExpansions.keys()));
      return;
    }
    
    const { addedNodeIds, addedLinkIds } = expansionInfo;
    logger.render('Nodes to remove:', Array.from(addedNodeIds));
    logger.render('Links to remove:', Array.from(addedLinkIds));
    
    // Debug: Check if the nodes to be removed are actually in the current data
    const currentNodeIds = new Set(filteredData.nodes.map(n => n.elementId));
    const nodesToRemove = Array.from(addedNodeIds).filter(id => currentNodeIds.has(id));
    logger.render('Nodes that will actually be removed (present in current data):', nodesToRemove);
    
    // Remove the nodes and links that were added by this expansion
    const filteredNodes = filteredData.nodes.filter(node => {
      const shouldKeep = !addedNodeIds.has(node.elementId);
      if (!shouldKeep) {
        logger.render('Removing node:', node.elementId, node.name || node.label);
      }
      return shouldKeep;
    });
    
    const filteredLinks = filteredData.links.filter(link => {
      const shouldKeep = !addedLinkIds.has(link.elementId);
      if (!shouldKeep) {
        logger.render('Removing link:', link.elementId, link.type);
      }
      return shouldKeep;
    });
    
    logger.render('Nodes before collapse:', filteredData.nodes.length, 'after:', filteredNodes.length);
    logger.render('Links before collapse:', filteredData.links.length, 'after:', filteredLinks.length);
    logger.render('Remaining node IDs:', filteredNodes.map(n => n.elementId));
    
    // Validate that we're actually removing nodes
    if (filteredNodes.length === filteredData.nodes.length) {
      logger.error('ERROR: No nodes were actually removed! This indicates a problem with the collapse logic.');
      logger.error('Check if addedNodeIds match the actual node elementIds');
      logger.error('addedNodeIds:', Array.from(addedNodeIds));
      logger.error('current node elementIds:', filteredData.nodes.map(n => n.elementId));
    }
    
    // Update datasets
    const newData = { nodes: filteredNodes, links: filteredLinks };
    logger.render('Setting new data:', {
      nodeCount: newData.nodes.length,
      linkCount: newData.links.length
    });
    
    setFilteredData(newData);
    setFullDataset(newData);
    setData(newData);
    setGraphData(newData);
    if (setSearchResults) {
      setSearchResults(newData.nodes);
    }
    
    // Remove this node from expanded set and expansion tracking
    setExpandedNodes(prev => {
      const newSet = new Set(prev);
      newSet.delete(nodeId);
      logger.render('Updated expandedNodes:', Array.from(newSet));
      return newSet;
    });
    
    setNodeExpansions(prev => {
      const newMap = new Map(prev);
      newMap.delete(nodeId);
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
        // Arrange nodes in a rough circle around center
        const angle = (index / nodes.length) * 2 * Math.PI;
        const radius = Math.min(width, height) * 0.2; // 20% of viewport size
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
    
    // Performance optimization: detect layout changes
    const layoutChanged = layoutType !== prevLayoutType;
    if (layoutChanged) {
      logger.render(`[SYNC] Layout changed from ${prevLayoutType} to ${layoutType}`);
      setPrevLayoutType(layoutType);
    }
    
    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

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
      
      defs.append("marker")
        .attr("id", "arrowhead") // Unique ID for the marker
        .attr("viewBox", `0 -${ARROW_HEAD_WIDTH / 2} ${ARROW_HEAD_LENGTH} ${ARROW_HEAD_WIDTH}`) // Viewbox for the marker content
        .attr("refX", ARROW_REF_X) // X coordinate of the reference point (where the arrow attaches to the line)
        .attr("refY", 0)           // Y coordinate of the reference point
        .attr("markerWidth", ARROW_HEAD_LENGTH)  // Size of the marker itself
        .attr("markerHeight", ARROW_HEAD_WIDTH)
        .attr("orient", "auto")    // Automatically rotates the arrow
        .append("path")
          .attr("d", `M0,-${ARROW_HEAD_WIDTH / 2}L${ARROW_HEAD_LENGTH},0L0,${ARROW_HEAD_WIDTH / 2}`) // Triangle shape
          .attr("fill", LINK_COLOR || '#999'); // Fill color of the arrow
      
      logger.render('D3 Arrowhead Marker defined in defs');
      
      gRef.current = svg.append('g'); // Main group for graph elements
      // Initialize zoom behavior on the parent SVG
      svg.call(d3.zoom()
        .scaleExtent([0.1, 5])
        .on('zoom', ({ transform }) => {
          gRef.current.attr('transform', transform);
        })
      );

      logger.render('D3 SVG initialized with marker in persistent defs.');
    }

    // Check if we have data to render - use full dataset if filteredData is empty and we have graphData
    const hasData = filteredData.nodes.length > 0 || (graphData.nodes && graphData.nodes.length > 0);
    const renderData = filteredData.nodes.length > 0 ? filteredData : 
                      (graphData.nodes && graphData.nodes.length > 0) ? graphData : 
                      { nodes: [], links: [] };

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
      .attr('fill', '#0066B3')
      .attr('stroke', 'white')
      .attr('stroke-width', '3')
      .attr('paint-order', 'stroke fill')
      .text(`Nodes: ${renderData.nodes.length}`);
    
    // Re-enable zoom for force-directed layout
    svg.call(d3.zoom()
      .scaleExtent([0.1, 5])
      .on('zoom', ({ transform }) => {
        gRef.current.attr('transform', transform);
      })
    );
    
    logger.render(`[TARGET] Initializing graph layout with ${renderData.nodes.length} nodes, ${renderData.links.length} links`);
    
    // Initialize positions for new nodes (especially for search results)
    initializeNodePositions(renderData.nodes, width, height);

    // --- Process links for bidirectional relationship separation ---
    const processedLinks = processLinksForOffset([...renderData.links]);
    
    logger.render('[LINK PROCESSING]', {
      inputLinks: renderData.links.length,
      processedLinks: processedLinks.length,
      sample: processedLinks.slice(0, 2).map(l => ({ source: l.source, target: l.target, type: l.type }))
    });

    // --- Initialize/Update Simulation ---
    if (!simulationRef.current) {
      simulationRef.current = d3.forceSimulation(renderData.nodes)
        .force('link', d3.forceLink(processedLinks).id(d => d.elementId).distance(LINK_DISTANCE))
        .force('charge', d3.forceManyBody().strength(CHARGE_STRENGTH))
        .force('center', d3.forceCenter(width / 2, height / 2).strength(CENTER_FORCE_STRENGTH))
        .force('collide', d3.forceCollide().radius(COLLIDE_RADIUS))
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
        simulationRef.current.force('boundary', boundaryForce(width, height));
        
        // Use lower alpha for smoother transitions, higher for layout changes
        const alpha = layoutChanged ? 0.5 : 0.3;
        simulationRef.current.alpha(alpha).restart();
        logger.render(`D3 Simulation updated with alpha ${alpha} (nodes changed: ${nodesChanged}, layout changed: ${layoutChanged})`);
      } else {
        logger.render('Skipping simulation update - no data changes detected');
      }
    }
 
    // --- D3 Data Binding and Drawing ---
    // Links (paths for curved bidirectional links, lines for single links)
    const link = gRef.current.selectAll('.link')
      .data(processedLinks, d => d.elementId)
      .join(
        enter => {
          logger.render('[LINK] Creating new links with marker-end attribute', enter.size());
          const group = enter.append('path')
            .attr('class', 'link')
            .attr('stroke', LINK_COLOR || '#999')
            .attr('stroke-opacity', LINK_OPACITY)
            .attr('stroke-width', LINK_STROKE_WIDTH)
            .attr('fill', 'none')  // Important for path elements
            .attr('marker-end', 'url(#arrowhead)')
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
                tooltipRef.current.style.pointerEvents = 'auto';
                tooltipRef.current.style.opacity = 0.9;
              }
              // Get relationship type from your query
              const relationshipType = d.type || 'Relationship';
              
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
              const srcNode = typeof d.source === 'object' ? d.source : (filteredData.nodes || []).find(n => n.elementId === d.source);
              const tgtNode = typeof d.target === 'object' ? d.target : (filteredData.nodes || []).find(n => n.elementId === d.target);
              const srcLabel = srcNode?.labels?.[0] || 'Node';
              const tgtLabel = tgtNode?.labels?.[0] || 'Node';
              
              tooltipContent += `<div style="margin: 8px; padding: 8px; background: #f8f9fa; border-radius: 4px; font-size: 11px; color: #495057;">
                <strong style="color: #0066B3;">From:</strong> ${srcLabel}<br/>
                <strong style="color: #28A745;">To:</strong> ${tgtLabel}
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
              }
            })
          

          return group;
        },
        update => update,
        exit => exit.remove()
    );

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
            .attr('fill', d => getNodeColor(d.label));

          // Highlight glow ring for "View in Graph" from Recommendations
          group.append('circle')
            .attr('class', 'rec-highlight-ring')
            .attr('r', NODE_RADIUS + 6)
            .attr('fill', 'none')
            .attr('stroke', '#FFD700')
            .attr('stroke-width', 3)
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
            .text(d => getPrimaryNodeLabel(d))
            .attr('font-size', 10)
            .attr('font-weight', 'bold')
            .attr('dx', NODE_RADIUS + 5)
            .attr('dy', 3)
            .attr('fill', '#000')
            .style('pointer-events', 'none');

          // Expand/Collapse control circle (only for search results)
          group.append('circle')
            .attr('class', 'expand-control-bg')
            .attr('r', EXPAND_CIRCLE_RADIUS)
            .attr('cx', NODE_RADIUS + 18)
            .attr('cy', -NODE_RADIUS - 2)
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
              logger.render('Is expanded:', expandedNodes.has(d.elementId));
              logger.render('Loading nodes:', Array.from(loadingNodes));
              logger.render('Current expandedNodes state:', Array.from(expandedNodes));
              logger.render('Current nodeExpansions state:', Array.from(nodeExpansions.keys()));
              
              // Direct check and call to avoid any dependency issues
              if (expandedNodes.has(d.elementId)) {
                logger.render('Node is expanded - calling collapseNode directly...');
                collapseNode(d.elementId);
              } else if (!expandedNodes.has(d.elementId) && hasExpandableConnections(d)) {
                logger.render('Node can be expanded - calling expandNode directly...');
                expandNode(d.elementId);
              } else {
                logger.render('No action taken - node cannot be expanded or collapsed');
              }
            });

          // Plus/Minus symbol
          group.append('text')
            .attr('class', 'expand-symbol')
            .attr('x', NODE_RADIUS + 18)
            .attr('y', -NODE_RADIUS + 2)
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
            .attr('stroke-width', 2)
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

            d3.select(this).select('.main-icon')
              .attr('stroke', 'black')
              .attr('stroke-width', 2);
            d3.select(this).select('.fallback-circle')
              .attr('stroke', 'black')
              .attr('stroke-width', 1.5);
            d3.select(tooltipRef.current).style('z-index', 12).style('pointer-events', 'auto');
            d3.select(tooltipRef.current).style('opacity', 0.9);
            
            // Get node type from labels (first label) - for HEADER
            const nodeType = (d.labels && d.labels.length > 0) ? d.labels[0] : 'Node';
            
            // Get properties - handle both nested and flat structure
            const props = d.properties && typeof d.properties === 'object' && !Array.isArray(d.properties) 
              ? d.properties 
              : d;
            
            // HEADER: Show the node label/type with close button
            let tooltipContent = buildTooltipHeader(nodeType, tooltipCloseBtn);
            // Recommendation action buttons (top, right after header)
            tooltipContent += buildRecActionBar(d.name || props.name, d.labels);
            
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
            const connectedLinks = (filteredData.links || []).filter(link => 
              link.source === d.elementId || link.target === d.elementId
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
            
            // SECTION: Data Properties (OntologyProperty nodes with PROPERTY_OF relationship)
            const dataProperties = connectedLinks.filter(link => 
              (link.type === 'PROPERTY_OF' && link.source === d.elementId) ||
              (link.type === 'PROPERTY_OF' && link.target === d.elementId)
            );
            
            if (dataProperties.length > 0) {
              tooltipContent += `<div style="margin-top: 12px; padding-top: 12px; border-top: 2px solid #e0e0e0;">
                <div style="font-weight: bold; color: #28A745; margin-bottom: 8px; font-size: 12px;">
                  <i class="fas fa-list" style="margin-right: 4px;"></i>Data Properties (${dataProperties.length})
                </div>`;
              
              dataProperties.forEach(link => {
                const isPropOwner = link.source === d.elementId;
                const propNodeId = isPropOwner ? link.target : link.source;
                const propNode = (filteredData.nodes || []).find(n => n.elementId === propNodeId);
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
                const isOutgoing = link.source === d.elementId;
                const otherNodeId = isOutgoing ? link.target : link.source;
                const otherNode = (filteredData.nodes || []).find(n => n.elementId === otherNodeId);
                const otherNodeName = otherNode?.name || otherNode?.label || 'Unknown';
                const otherNodeType = otherNode?.label || otherNode?.labels?.[0] || 'Node';
                const relationshipType = escapeHtml(link.type || 'UNKNOWN');
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
            }
          })
          .on('mouseout', function () {
            d3.select(this).select('.main-icon')
              .attr('stroke', null)
              .attr('stroke-width', null);
            d3.select(this).select('.fallback-circle')
              .attr('stroke', null)
              .attr('stroke-width', null);
          });

          return group;
        },
        update => {
          // Update circle color based on label
          update.select('.node-circle')
            .attr('fill', d => getNodeColor(d.label));
          
          update.select('.node-label')
            .text(d => getPrimaryNodeLabel(d))
            .attr('font-weight', 'bold')
            .attr('fill', '#000');

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
 
    simulationRef.current.on('tick', () => {
      // Use requestAnimationFrame for smoother performance
      requestAnimationFrame(() => {
        // Only update link paths (heavy operation)
        link.each(function(d) {
          const sourceX = d.source.x;
          const sourceY = d.source.y;
          const targetX = d.target.x;
          const targetY = d.target.y;
          
          // Calculate curved path for bidirectional links, straight for single links
          const pathData = calculateCurvedPath(d, sourceX, sourceY, targetX, targetY);
          
          d3.select(this)
            .attr('d', pathData);
        });
        
        // Update node positions (lighter operation)
        node.attr('transform', d => `translate(${d.x},${d.y})`);
      });
    });

    // Center the view on search results
    if (searchQuery && filteredData.nodes.length > 0) {
      // Calculate the bounding box of all nodes
      const nodePositions = filteredData.nodes.map(d => ({x: d.x || 0, y: d.y || 0}));
      const minX = Math.min(...nodePositions.map(d => d.x));
      const maxX = Math.max(...nodePositions.map(d => d.x));
      const minY = Math.min(...nodePositions.map(d => d.y));
      const maxY = Math.max(...nodePositions.map(d => d.y));
      
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      
      // Apply transform to center the search results
      const transform = d3.zoomIdentity
        .translate(width / 2 - centerX, height / 2 - centerY)
        .scale(1);
      
      svg.call(
        d3.zoom().transform,
        transform
      );
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
      if (simulationRef.current) {
        simulationRef.current.stop();
        simulationRef.current = null; // Clear reference for memory cleanup
        performanceLog('D3 Simulation stopped and cleared on component unmount.');
      }
      // Clear any remaining event listeners
      if (gRef.current) {
        gRef.current.selectAll('*').on('.drag', null);
      }
    };
 
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredData, layoutType, treeExpandedNodes]);

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
          .attr('stroke-width', 3)
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
        rect.attr('fill', '#FFF9C4').attr('stroke', '#FFD700').attr('stroke-width', 2);
      }
    });
  }, [highlightedNodeNames]);

  // Keyboard shortcuts for expand/collapse
  useEffect(() => {
    const handleKeyPress = (event) => {
      if (event.key === 'Escape') {
        // Collapse all nodes and reset to original search results
        setExpandedNodes(new Set());
        setNodeExpansions(new Map());
        setFilteredData(graphData);
        setFullDataset(graphData);
        setData(graphData);
        if (setSearchResults) {
          setSearchResults(graphData.nodes);
        }
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData]);

  // Reset expanded nodes when search query changes
  useEffect(() => {
    setExpandedNodes(new Set());
    setNodeExpansions(new Map());
  }, [searchQuery]);

  // [OK] CLEANUP: Final cleanup on component unmount
  useEffect(() => {
    const timeouts = timeoutsRef.current;
    const simulation = simulationRef.current;
    return () => {
      // Clear all pending timeouts
      if (timeouts) {
        timeouts.forEach(id => clearTimeout(id));
        timeouts.clear();
      }
      // Stop D3 simulation if running
      if (simulation) {
        simulation.stop();
        simulationRef.current = null;
      }
      // Clean up window listeners
      window.removeEventListener('dt-highlight-nodes', null);
      window.removeEventListener('dt-load-result-nodes', null);
      window.removeEventListener('keydown', null);
    };
  }, []);

  return (
    <div
      className="graph-heb-root"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        backgroundColor: '#fafbfc',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* STATIC TOOLBAR (prevents overlap with graph + tree layouts) */}
      <div
        className="graph-toolbar"
        style={{
          display:'flex',
          gap:'12px',
          alignItems:'center',
          flexWrap:'wrap',
          padding:'10px 14px',
          background:'#ffffff',
          border:'1px solid #e2e6ea',
          borderRadius:'8px',
          boxShadow:'0 2px 6px rgba(0,0,0,0.08)',
          zIndex:1500, // raise above potential header overlay
          position:'relative'
        }}
      >
        <div className="dropdown" style={{ position:'relative' }}>
          <button
            className="btn btn-sm dropdown-toggle"
            type="button"
            title="Graph tools"
            onClick={(e)=>{
              const menu = e.currentTarget.nextSibling; if(menu) menu.classList.toggle('show');
            }}
            style={{
              backgroundColor:'#fff',
              color:'#004B87',
              fontWeight:700,
              border:'1px solid #cfd6dc',
              borderRadius:6,
              padding:'5px 9px',
              fontSize:12,
              lineHeight:1.2
            }}
          >Tools</button>
          <div
            className="dropdown-menu p-1"
            style={{
              minWidth:150,
              background:'#fff',
              color:'#243b53',
              border:'1px solid #cfd6dc',
              boxShadow:'0 4px 12px rgba(16,42,67,0.14)',
              position:'absolute',
              top:'100%',
              left:0,
              marginTop:4,
              zIndex:2000
            }}
          >
            {[
              ['Where Used', 'whereused'],
              ['Table View', 'table'],
              ['Reports', 'reports'],
              ['Data Import', 'ingestion'],
              ['Map & Align', 'ontology'],
              ['Recommendations', 'recommendations'],
              ['Admin', 'admin'],
            ].map(([label, target]) => (
              <button
                key={target}
                className="dropdown-item"
                style={{ color:'#243b53', fontSize:12, fontWeight:600, cursor:'pointer', padding:'5px 8px' }}
                onClick={(e)=>{
                  e.currentTarget.closest('.dropdown-menu')?.classList.remove('show');
                  if(typeof setActiveTab==='function'){ setActiveTab(target); }
                }}
              >{label}</button>
            ))}
          </div>
        </div>
        <div style={{ width: 1, height: 24, background: '#d0d7de', margin: '0 2px' }} />
        {/* ── Graph View Mode selector ─────────────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <i className="fas fa-layer-group" style={{ fontSize: '14px', color: '#004B87' }}></i>
          <select
            value={graphViewMode}
            onChange={e => setGraphViewMode(e.target.value)}
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid #cfd6dc',
              backgroundColor: '#fff',
              color: '#333',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: 500,
              minWidth: '240px',
              transition: 'all .2s ease'
            }}
            title="Switch between Ontology Graph and Individual Contextual Graph"
          >
            <option value="ontology" style={{color:'#333', fontWeight:600}}>Ontology Graph Visualization</option>
            <option value="individual" style={{color:'#333', fontWeight:600}}>Contextual Individual Graph View</option>
          </select>
        </div>
        {/* Divider */}
        <div style={{ width: 1, height: 28, background: '#d0d7de', margin: '0 2px' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <i className="fas fa-search" style={{ fontSize: '18px', color: '#555' }}></i>
          <input
            type="text"
            placeholder="Search nodes..."
            value={searchInput}
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid #cfd6dc',
              minWidth: '190px',
              fontSize: '13px',
              fontWeight: 500,
              lineHeight: 1.2,
              background: '#fff',
              color: '#333'
            }}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') setSearchQuery(e.target.value); }}
            onFocus={e => { e.target.style.borderColor = '#004B87'; e.target.style.boxShadow='0 0 0 2px rgba(0,75,135,0.15)'; }}
            onBlur={e => { e.target.style.borderColor = '#cfd6dc'; e.target.style.boxShadow='none'; }}
          />
        </div>
        {/* Label filter dropdown — only visible when search has results */}
        {availableLabels.length > 0 && searchQuery && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <i className="fas fa-filter" style={{ fontSize: '14px', color: '#555' }}></i>
            <select
              value={selectedLabelFilter}
              onChange={e => setSelectedLabelFilter(e.target.value)}
              style={{
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid #cfd6dc',
                backgroundColor: '#fff',
                color: '#333',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: 500,
                minWidth: '150px',
                transition: 'all .2s ease'
              }}
              title="Filter search results by node label"
            >
              <option key="ALL" value="ALL">All Labels ({searchResultData.nodes.length})</option>
              {availableLabels.map(label => {
                const count = searchResultData.nodes.filter(n => (n.labels || []).includes(label)).length;
                return (
                  <option key={label} value={label}>
                    {label} ({count})
                  </option>
                );
              })}
            </select>
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <i className="fas fa-chart-bar" style={{ fontSize: '14px', color: '#555' }}></i>
          <select
            value={layoutType}
            onChange={(e) => handleLayoutChange(e.target.value)}
            disabled={isLayoutSwitching || searchLoading}
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid #cfd6dc',
              backgroundColor: '#fff',
              color: '#333',
              cursor: isLayoutSwitching ? 'not-allowed' : 'pointer',
              fontSize: '13px',
              fontWeight: 500,
              minWidth: '180px',
              transition: 'all .2s ease',
              opacity: isLayoutSwitching ? 0.6 : 1
            }}
            title={isLayoutSwitching ? 'Layout switching in progress...' : 'Select graph layout type'}
          >
            <option key="force-directed" value="force-directed" style={{color:'#333'}}>Force-Directed Graph</option>
            <option key="indented-tree" value="indented-tree" style={{color:'#333'}}>Indented Tree Layout</option>
          </select>
        </div>
        
        {/* Ontology selector dropdown — only in Ontology Graph mode */}
        {graphViewMode === 'ontology' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <i className="fas fa-project-diagram" style={{ fontSize: '14px', color: '#555' }}></i>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <select
              value={selectedOntology}
              onChange={e => setSelectedOntology(e.target.value)}
              disabled={ontologyLoading || !!ontologyError}
              style={{
                padding: '6px 10px',
                borderRadius: '6px',
                border: ontologyError ? '1px solid #D32F2F' : '1px solid #cfd6dc',
                backgroundColor: '#fff',
                color: '#333',
                cursor: ontologyLoading || ontologyError ? 'not-allowed' : 'pointer',
                fontSize: '13px',
                fontWeight: 500,
                minWidth: '200px',
                transition: 'all .2s ease',
                opacity: ontologyLoading || ontologyError ? 0.6 : 1
              }}
              title={ontologyError ? ontologyError : "Select ontology to view"}
            >
              <option value="ALL" style={{color:'#333', fontWeight:600}}>— All Ontologies (Full Graph) —</option>
              {ontologyOptions.filter(o => o.value !== 'ALL' && !o.disabled).map((opt, idx) => (
                <option key={opt.value || `ontology-opt-${idx}`} value={opt.value} style={{color:'#333'}}>
                  {opt.prefix ? `[${opt.prefix}] ` : ''}{opt.label}{opt.type ? ` · ${opt.type}` : ''}{Number(opt.relationship_count || 0) === 0 ? ' · classes only' : ''}
                </option>
              ))}
            </select>
            {ontologyError && <span style={{ fontSize: '11px', color: '#D32F2F' }}>Warning: {ontologyError}</span>}
          </div>
        </div>
        )}
        {/* STEP part sub-filter — only in Ontology mode and STEP selected */}
        {graphViewMode === 'ontology' && selectedOntology === 'step' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <i className="fas fa-cogs" style={{ fontSize: '14px', color: '#555' }}></i>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <select
                value={selectedStepPart}
                onChange={e => setSelectedStepPart(e.target.value)}
                disabled={stepPartsLoading || ontologyLoading || !!stepPartsError}
                style={{
                  padding: '6px 10px',
                  borderRadius: '6px',
                  border: stepPartsError ? '1px solid #D32F2F' : '1px solid #cfd6dc',
                  backgroundColor: '#fff',
                  color: '#333',
                  cursor: stepPartsLoading || ontologyLoading || stepPartsError ? 'not-allowed' : 'pointer',
                  fontSize: '13px',
                  fontWeight: 500,
                  minWidth: '200px',
                  maxWidth: '320px',
                  transition: 'all .2s ease',
                  opacity: stepPartsLoading || ontologyLoading || stepPartsError ? 0.6 : 1
                }}
                title={stepPartsError ? stepPartsError : "Filter STEP data by part"}
              >
                <option key="ALL" value="ALL" style={{color:'#333'}}>All Parts{stepParts.length > 0 ? ` (${stepParts.length})` : ''}</option>
                {stepParts.map(part => (
                  <option key={part} value={part} style={{color:'#333'}}>
                    {part.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
              {stepPartsError && <span style={{ fontSize: '11px', color: '#D32F2F' }}>Warning: {stepPartsError}</span>}
            </div>
          </div>
        )}
        {(searchLoading || isLayoutSwitching || ontologyLoading) && (
          <div style={{display:'flex', alignItems:'center', gap:6, fontSize:13, color:'#004B87'}}>
            <div className="spinner" style={{width:14,height:14,border:'2px solid #f3f3f3',borderTop:'2px solid #004B87',borderRadius:'50%',animation:'spin 1s linear infinite'}}></div>
            {searchLoading ? 'Searching...' : ontologyLoading ? 'Loading ontology...' : 'Switching layout...'}
          </div>
        )}
        {ontologyGraphMessage && (
          <div style={{fontSize:12, color:'#8a5a00', background:'#fff8e1', border:'1px solid #ffe082', borderRadius:5, padding:'5px 8px'}}>
            {ontologyGraphMessage}
          </div>
        )}
        {(searchQuery || selectedOntology !== 'ALL' || graphViewMode !== 'ontology') && (
          <button
            onClick={() => {
              setGraphViewMode('ontology');
              graphViewModeRef.current = 'ontology';
              setSearchQuery('');
              setSearchInput('');
              setSelectedLabelFilter('ALL');
              setAvailableLabels([]);
              setSearchResultData({ nodes: [], links: [] });
              setSelectedOntology('ALL');
              setSelectedStepPart('ALL');
              setStepParts([]);
              setExpandedNodes(new Set());
              setNodeExpansions(new Map());
              setData(initialData);
              setGraphData(initialData);
              setFilteredData(initialData);
              setFullDataset(initialData);
              if (setSearchResults) setSearchResults(initialData.nodes);
            }}
            style={{padding:'6px 12px', border:'none', borderRadius:'6px', backgroundColor:'#004B87', color:'#fff', fontSize:'13px', fontWeight:600, cursor:'pointer', transition:'all .2s ease'}}
          >Reset</button>
        )}
        <button
          onClick={toggleChat}
          style={{padding:'6px 12px', border:'none', borderRadius:'6px', backgroundColor:'#004B87', color:'#fff', fontSize:'13px', fontWeight:600, cursor:'pointer', transition:'all .2s ease'}}
          title={showChat ? 'Hide chat assistant' : 'Show chat assistant'}
        >{showChat ? 'Hide Chat' : 'Show Chat'}</button>
      </div>
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
      {!isLoading && !error && filteredData.nodes.length === 0 && debouncedSearchQuery && (
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
      {!isLoading && !error && graphData.nodes.length === 0 && !searchQuery && (
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
 
  <svg ref={svgRef} style={{ width: '100%', height: '100%', flexGrow: 1, margin: 0, padding: 0 }}></svg>
 
      <div ref={tooltipRef} className="tooltip" style={{
        position: 'absolute', 
        opacity: 1, 
        background: 'rgba(0,0,0,0.7)', 
        color: 'white',
        padding: '8px', 
        borderRadius: '4px', 
        pointerEvents: 'auto', 
        maxWidth: '300px', 
        fontSize: '0.8em', 
        zIndex: 12,
        display: 'block'
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
      
      {/* Comparative Search Modal - Disabled */}
      {false && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <div style={{
            backgroundColor: 'white',
            borderRadius: '8px',
            width: '90vw',
            height: '85vh',
            maxWidth: '1400px',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
          }}>
            {/* Header */}
            <div style={{
              padding: '16px 24px',
              borderBottom: '1px solid #e0e0e0',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              backgroundColor: '#333333'
            }}>
              <h2 style={{ margin: 0, color: '#ffffff', fontSize: '20px' }}>Comparative Node Analysis</h2>
              <button
                onClick={() => { /* Modal closed */ }}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '24px',
                  cursor: 'pointer',
                  color: '#ffffff'
                }}
              >
                {CHAR_TIMES}
              </button>
            </div>
            
            {/* Keyword Search & Selection for Comparison */}
            <div style={{ padding: '20px', borderBottom: '1px solid #e0e0e0', backgroundColor: '#f8f9fa' }}>
              <div style={{ display: 'flex', gap: '24px' }}>
                {/* Node A Column */}
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <h3 style={{ margin: 0, color: '#0066B3', fontSize: 16 }}>Node A</h3>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      type="text"
                      value={compareTermA}
                      placeholder="Search keyword (name, version...)"
                      onChange={e => setCompareTermA(e.target.value)}
                      onKeyDown={e => e.key==='Enter' && performKeywordCompareSearch('A', compareTermA)}
                      style={{ flex:1, padding:'8px 12px', border:'1px solid #dde2e6', borderRadius:4, fontSize:14 }}
                    />
                    <button
                      onClick={()=>performKeywordCompareSearch('A', compareTermA)}
                      disabled={isCompareSearching.A || !compareTermA.trim()}
                      style={{ padding:'8px 14px', background: isCompareSearching.A? 'rgba(10,130,118,0.6)': primaryButtonColor, color:'#fff', border:'none', borderRadius:4, cursor: isCompareSearching.A? 'not-allowed':'pointer', transition:'background-color 0.15s' }}
                    >{isCompareSearching.A ? 'Searching...' : 'Search'}</button>
                  </div>
                  {selectedCompareNodeA && (
                    <div style={{ fontSize:12, background:'#e9f2fb', padding:'6px 8px', borderRadius:4, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                      <span><strong>Selected:</strong> {getNodeShortLabel(selectedCompareNodeA)}</span>
                      <button onClick={()=> setSelectedCompareNodeA(null)} style={{ background:'none', border:'none', color:'#0066B3', cursor:'pointer', fontSize:12 }}>{CHAR_TIMES}</button>
                    </div>
                  )}
                  {compareResultsA.length > 0 && (
                    <div style={{ display:'flex', flexWrap:'wrap', gap:8, maxHeight:140, overflowY:'auto', background:'#fff', border:'1px solid #ddd', padding:8, borderRadius:4 }}>
                      {compareResultsA.map(n => (
                        <button key={n.elementId}
                          onClick={()=> setSelectedCompareNodeA(n)}
                          style={{
                            padding:'6px 10px',
                            background: selectedCompareNodeA?.elementId === n.elementId ? '#0066B3':'#f1f3f5',
                            color: selectedCompareNodeA?.elementId === n.elementId ? '#fff':'#333',
                            border:'1px solid #ccc',
                            borderRadius:4,
                            cursor:'pointer',
                            fontSize:12
                          }}
                        >{getNodeShortLabel(n)}</button>
                      ))}
                    </div>
                  )}
                </div>
                {/* Node B Column */}
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <h3 style={{ margin: 0, color: '#FF6600', fontSize: 16 }}>Node B</h3>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      type="text"
                      value={compareTermB}
                      placeholder="Search keyword (name, version...)"
                      onChange={e => setCompareTermB(e.target.value)}
                      onKeyDown={e => e.key==='Enter' && performKeywordCompareSearch('B', compareTermB)}
                      style={{ flex:1, padding:'8px 12px', border:'1px solid #dde2e6', borderRadius:4, fontSize:14 }}
                    />
                    <button
                      onClick={()=>performKeywordCompareSearch('B', compareTermB)}
                      disabled={isCompareSearching.B || !compareTermB.trim()}
                      style={{ padding:'8px 14px', background: isCompareSearching.B? 'rgba(10,130,118,0.6)': primaryButtonColor, color:'#fff', border:'none', borderRadius:4, cursor: isCompareSearching.B? 'not-allowed':'pointer', transition:'background-color 0.15s' }}
                    >{isCompareSearching.B ? 'Searching...' : 'Search'}</button>
                  </div>
                  {selectedCompareNodeB && (
                    <div style={{ fontSize:12, background:'#fff2e6', padding:'6px 8px', borderRadius:4, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                      <span><strong>Selected:</strong> {getNodeShortLabel(selectedCompareNodeB)}</span>
                      <button onClick={()=> setSelectedCompareNodeB(null)} style={{ background:'none', border:'none', color:'#FF6600', cursor:'pointer', fontSize:12 }}>{CHAR_TIMES}</button>
                    </div>
                  )}
                  {compareResultsB.length > 0 && (
                    <div style={{ display:'flex', flexWrap:'wrap', gap:8, maxHeight:140, overflowY:'auto', background:'#fff', border:'1px solid #ddd', padding:8, borderRadius:4 }}>
                      {compareResultsB.map(n => (
                        <button key={n.elementId}
                          onClick={()=> setSelectedCompareNodeB(n)}
                          style={{
                            padding:'6px 10px',
                            background: selectedCompareNodeB?.elementId === n.elementId ? '#FF6600':'#f1f3f5',
                            color: selectedCompareNodeB?.elementId === n.elementId ? '#fff':'#333',
                            border:'1px solid #ccc',
                            borderRadius:4,
                            cursor:'pointer',
                            fontSize:12
                          }}
                        >{getNodeShortLabel(n)}</button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div style={{ display:'flex', gap:12, marginTop:16, alignItems:'center', flexWrap:'wrap' }}>
                <button
                  onClick={openComparisonPopup}
                  disabled={!selectedCompareNodeA || !selectedCompareNodeB || selectedCompareNodeA.elementId === selectedCompareNodeB.elementId}
                  style={{ padding:'10px 18px', background: (!selectedCompareNodeA || !selectedCompareNodeB || selectedCompareNodeA.elementId === selectedCompareNodeB.elementId)? '#adb5bd':'#343a40', color:'#fff', border:'none', borderRadius:4, cursor:(!selectedCompareNodeA || !selectedCompareNodeB || selectedCompareNodeA.elementId === selectedCompareNodeB.elementId)? 'not-allowed':'pointer' }}
                >Show Comparison (Popup)</button>
                {(selectedCompareNodeA || selectedCompareNodeB) && (
                  <button onClick={()=>{ setSelectedCompareNodeA(null); setSelectedCompareNodeB(null); setCompareResultsA([]); setCompareResultsB([]); setCompareTermA(''); setCompareTermB(''); setPropertyComparisonData(null); }} style={{ padding:'8px 14px', background:'#6c757d', color:'#fff', border:'none', borderRadius:4, cursor:'pointer', marginLeft:8 }}>Reset</button>
                )}
              </div>
            </div>

            {/* Property Comparison Results */}
            <div style={{ flex:1, overflow:'auto', padding:20 }}>
              {propertyComparisonData ? (
                <div>
                  <h3 style={{ margin:'0 0 12px 0', color:'#2C2C2C' }}>Property Comparison (All Properties)</h3>
                  <div style={{ display:'grid', gridTemplateColumns:'220px 1fr 1fr 110px', fontSize:12, border:'1px solid #dee2e6', borderRadius:4 }}>
                    <div style={{ fontWeight:'bold', padding:'8px', background:'#f1f3f5', borderBottom:'1px solid #dee2e6', borderRight:'1px solid #dee2e6' }}>Property</div>
                    <div style={{ fontWeight:'bold', padding:'8px', background:'#e9ecef', borderBottom:'1px solid #dee2e6', borderRight:'1px solid #dee2e6' }}>Node A</div>
                    <div style={{ fontWeight:'bold', padding:'8px', background:'#e9ecef', borderBottom:'1px solid #dee2e6', borderRight:'1px solid #dee2e6' }}>Node B</div>
                    <div style={{ fontWeight:'bold', padding:'8px', background:'#f1f3f5', borderBottom:'1px solid #dee2e6' }}>Status</div>
                    {propertyComparisonData.rows.map(r => {
                      const bgA = r.status === 'left_only' ? '#fff3cd' : r.status === 'different' ? '#f8f9fa' : '#ffffff';
                      const bgB = r.status === 'right_only' ? '#ffe5d0' : r.status === 'different' ? '#f8f9fa' : '#ffffff';
                      return (
                        <React.Fragment key={r.property}>
                          <div style={{ padding:'6px 8px', borderBottom:'1px solid #f1f3f5', borderRight:'1px solid #f1f3f5', fontWeight: r.status !== 'same' ? '600':'400' }}>{r.property}</div>
                          <div style={{ padding:'6px 8px', borderBottom:'1px solid #f1f3f5', borderRight:'1px solid #f1f3f5', background:bgA, fontFamily:'monospace', whiteSpace:'pre-wrap' }}>{typeof r.left === 'object' ? JSON.stringify(r.left) : String(r.left)}</div>
                          <div style={{ padding:'6px 8px', borderBottom:'1px solid #f1f3f5', borderRight:'1px solid #f1f3f5', background:bgB, fontFamily:'monospace', whiteSpace:'pre-wrap' }}>{typeof r.right === 'object' ? JSON.stringify(r.right) : String(r.right)}</div>
                          <div style={{ padding:'6px 8px', borderBottom:'1px solid #f1f3f5', textTransform:'capitalize', color: r.status==='different' ? '#d9534f' : r.status==='same' ? '#198754' : '#343a40' }}>{r.status.replace('_',' ')}</div>
                        </React.Fragment>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100%', color:'#2C2C2C', fontSize:16 }}>
                  {(!selectedCompareNodeA || !selectedCompareNodeB) ? 'Select two nodes to compare their properties.' : 'Click "Show Comparison" to generate property differences.'}
                </div>
              )}
            </div>
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

// Memoize component to prevent unnecessary re-renders.
export default React.memo(GraphHEB, (prevProps, nextProps) => {
  // Custom comparison: only re-render if specific props change
  return (
    prevProps.graphData === nextProps.graphData &&
    prevProps.onNodeClick === nextProps.onNodeClick &&
    prevProps.onLinkClick === nextProps.onLinkClick &&
    prevProps.selectedNode === nextProps.selectedNode &&
    prevProps.selectedLink === nextProps.selectedLink &&
    prevProps.highlightedNodes === nextProps.highlightedNodes &&
    prevProps.chatResults === nextProps.chatResults
  );
});
