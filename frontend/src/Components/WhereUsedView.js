import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import * as d3 from 'd3';
import '../App.css';
import config from '../config';
import { useSchema } from '../SchemaContext';
import { buildTooltipHeader } from './tooltipBuilder';
import logger from '../utils/logger';

// ──── DEVELOPER CONFIG: Node Display Label ────────────────────────────────
//
// DISPLAY_NAME_PROPERTY  — priority-ordered list of node properties to try.
//   The first property found on a node is used as the display name.
//   Set to [] (empty array) to rely solely on the Neo4j label.
const DISPLAY_NAME_PROPERTY = ['name', 'title', 'code', 'key', 'abbreviation', 'id'];
// const DISPLAY_NAME_PROPERTY = ['title', 'name'];
// const DISPLAY_NAME_PROPERTY = [];                // ← Neo4j label only
//
// DISPLAY_MODE  — controls what is shown in the node label.
//   'both-label-first'  → "Label - PropertyValue"   (default)
//   'both-prop-first'   → "PropertyValue (Label)"
//   'label-only'        → "Label"
//   'property-only'     → "PropertyValue"
const DISPLAY_MODE = 'both-label-first';
// const DISPLAY_MODE = 'both-prop-first';
// const DISPLAY_MODE = 'label-only';
// const DISPLAY_MODE = 'property-only';
// ───────────────────────────────────────────────────────────────────────────

// Helper: resolve the first matching property from DISPLAY_NAME_PROPERTY list
const resolveDisplayProp = (props) => {
  if (!props || !DISPLAY_NAME_PROPERTY || DISPLAY_NAME_PROPERTY.length === 0) return null;
  for (const key of DISPLAY_NAME_PROPERTY) {
    if (props[key] != null) return String(props[key]);
  }
  return null;
};

// Helper: format a display string from a Neo4j label and a property value
const formatNodeDisplay = (label, propValue) => {
  switch (DISPLAY_MODE) {
    case 'label-only':
      return label || propValue || 'Unknown';
    case 'property-only':
      return propValue || label || 'Unknown';
    case 'both-prop-first':
      if (!propValue) return label || 'Unknown';
      if (!label) return propValue;
      return `${propValue} (${label})`;
    case 'both-label-first':
    default:
      if (!propValue) return label || 'Unknown';
      if (!label) return propValue;
      return `${label} - ${propValue}`;
  }
};

const WhereUsedView = ({
    data,
    setData,
    searchResults,
    setSearchResults,
    chatResults,
    setChatResults,
    visibleRelationships,
    setVisibleRelationships,
    setActiveTab,
    showChat,
    toggleChat
}) => {
    const [searchTerm, setSearchTerm] = useState('');
    // Local hierarchy search results (distinct from global graph searchResults passed via props)
    const [hierarchySearchResults, setHierarchySearchResults] = useState([]);
    const [isSearching, setIsSearching] = useState(false);
    const [searchError, setSearchError] = useState(null);
    const [selectedNode, setSelectedNode] = useState(null);
    const [treeData, setTreeData] = useState(null);
    const [isExpandingUpwards, setIsExpandingUpwards] = useState(false);
    const [autoExpanded, setAutoExpanded] = useState(false);
    const [expansionError, setExpansionError] = useState(null);
    const [levels, setLevels] = useState([]); // Array of arrays: ancestors by distance
    const svgRef = useRef();
    // Schema-driven display
    const { getDisplayName: schemaDisplayName } = useSchema() || {};
    // Removed viewMode toggle; always show hierarchy view per latest requirements
    
    // Generic hash-based color generation (consistent with GraphHEB.js)
    const getNodeColor = (label) => {
        if (!label) return '#999';
        let hash = 0;
        for (let i = 0; i < label.length; i++) {
            hash = label.charCodeAt(i) + ((hash << 5) - hash);
        }
        const hue = Math.abs(hash) % 360;
        return `hsl(${hue}, 65%, 55%)`;
    };
    
    // Unified primary button color per request
    const primaryButtonColor = 'rgb(10, 130, 118)';

    // Unified search using same backend logic as GraphHEB (POST /graphfilter)
    const handleSearch = async () => {
        const term = searchTerm.trim();
        if (!term) return;
        setIsSearching(true);
        setSearchError(null);
        try {
            // Use graphfilter endpoint similar to GraphHEB implementation
            const response = await axios.post(`${config.apiUrl}/graphfilter`, { search: term.toLowerCase() });
            const records = response.data?.results || [];
            if (records.length === 0) {
                setHierarchySearchResults([]);
                setIsSearching(false);
                return;
            }
            // Extract nodes like in GraphHEB
            const nodesMap = new Map();
            records.forEach(record => {
                const n = record['n'];
                const r = record['r'];
                const m = record['m'];
                if (n) {
                    const nodeIdN = n.elementId;
                    const nodeN = {
                        ...n.properties,
                        elementId: nodeIdN,
                        labels: n.labels || ['Node'],
                        label: n.labels?.[0] || 'Node'
                    };
                    if (!nodesMap.has(nodeIdN)) nodesMap.set(nodeIdN, nodeN);
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
            const nodes = Array.from(nodesMap.values());
            setHierarchySearchResults(nodes);
        } catch (err) {
            logger.search('Search error (server):', err);
            // Fallback to client-side filtering of provided data
            try {
                const fallbackNodes = (data?.nodes || []).filter(n => {
                    const name = (n.name || '').toLowerCase();
                    const version = (n.external_version || n.version || '').toLowerCase();
                    return name.includes(term.toLowerCase()) || version.includes(term.toLowerCase());
                });
                setHierarchySearchResults(fallbackNodes);
                setSearchError('Server search failed. Showing local filtered results.');
            } catch (fe) {
                setHierarchySearchResults([]);
                setSearchError('Search failed.');
            }
        } finally {
            setIsSearching(false);
        }
    };

    // Upward expansion logic: recursively fetch parents via graphtraverse until top-level
    const expandAllParents = async (startNode) => {
        if (!startNode) return;
        setIsExpandingUpwards(true);
        setExpansionError(null);
        try {
            const ancestorMap = new Map();
            const linkSet = new Map(); // key: elementId
            const visited = new Set();
            const queue = [{ node: startNode, level: 0 }];
            ancestorMap.set(startNode.elementId, startNode);

            while (queue.length > 0) {
                const current = queue.shift();
                const currentNode = current.node;
                const currentLevel = current.level;
                if (visited.has(currentNode.elementId)) continue;
                visited.add(currentNode.elementId);

                // Call traverse API for current node
                try {
                    const resp = await axios.get(`${config.apiUrl}/graphtraverse/${currentNode.elementId}`);
                    const records = resp.data?.results || [];
                    records.forEach(record => {
                        const n = record['n'];
                        const r = record['r'];
                        const m = record['m'];
                        if (!r) return;
                        // Relationship direction: r.start -> r.end
                        // We want parents of current node: links where current is target (r.end === currentNode.elementId)
                        if (r.end === currentNode.elementId) {
                            // Parent is r.start
                            const parentNodeRaw = (n && n.elementId === r.start) ? n : (m && m.elementId === r.start ? m : null);
                            if (parentNodeRaw) {
                                const parentNode = {
                                    ...parentNodeRaw.properties,
                                    elementId: parentNodeRaw.elementId,
                                    labels: parentNodeRaw.labels || ['Node'],
                                    label: parentNodeRaw.labels?.[0] || 'Node'
                                };
                                if (!ancestorMap.has(parentNode.elementId)) {
                                    ancestorMap.set(parentNode.elementId, parentNode);
                                    queue.push({ node: parentNode, level: currentLevel + 1 });
                                }
                                if (!linkSet.has(r.elementId)) {
                                    linkSet.set(r.elementId, {
                                        elementId: r.elementId,
                                        source: r.start,
                                        target: r.end,
                                        type: r.type,
                                        properties: r.properties
                                    });
                                }
                            }
                        }
                    });
                } catch (e) {
                        logger.warn('Traverse fetch failed for %s: %s', currentNode.elementId, e.message);
                }
            }

            // Organize nodes into levels (distance from selected node upward)
            const levelMap = new Map();
            // We'll BFS again using links to compute distance (already tracked during traversal via queue level)
            // Reconstruct levels from queue processing by computing minimal distance using parent relationships
            ancestorMap.forEach((node, id) => {
                if (id === startNode.elementId) {
                    if (!levelMap.has(0)) levelMap.set(0, []);
                    levelMap.get(0).push(node);
                }
            });
            // We stored levels during queue pushes; recompute by exploring parents from start node:
            const distances = new Map();
            distances.set(startNode.elementId, 0);
            const parentLinks = Array.from(linkSet.values());
            const pending = [startNode.elementId];
            while (pending.length) {
                const childId = pending.shift();
                const childDist = distances.get(childId);
                parentLinks.forEach(l => {
                    if (l.target === childId) {
                        const parentId = l.source;
                        if (!distances.has(parentId) || distances.get(parentId) > childDist + 1) {
                            distances.set(parentId, childDist + 1);
                            pending.push(parentId);
                        }
                    }
                });
            }
            distances.forEach((dist, nodeId) => {
                const nodeObj = ancestorMap.get(nodeId);
                if (!levelMap.has(dist)) levelMap.set(dist, []);
                levelMap.get(dist).push(nodeObj);
            });
            const sortedLevels = Array.from(levelMap.entries()).sort((a,b) => b[0]-a[0]).map(e => e[1]); // top ancestors first
            
            logger.data('WhereUsed - Hierarchy built:');
            logger.data('  Total nodes: %d', Array.from(ancestorMap.values()).length);
            logger.data('  Total links: %d', parentLinks.length);
            logger.data('  Levels: %d', sortedLevels.length);
            sortedLevels.forEach((level, idx) => {
                logger.data('  Level %d: %d nodes', idx, level.length);
            });
            
            setLevels(sortedLevels);
            setTreeData({
                nodes: Array.from(ancestorMap.values()),
                links: parentLinks,
                root: startNode
            });
            setAutoExpanded(true);
        } catch (err) {
            setExpansionError(err.message);
        } finally {
            setIsExpandingUpwards(false);
        }
    };

    // Select node and build tree
    const handleNodeSelect = (node) => {
        setSelectedNode(node);
        setTreeData(null);
        setLevels([]);
        setAutoExpanded(false);
        expandAllParents(node);
    };

    // Render tree with D3
    // Zoom behavior stored in ref for reset button access across renders
    const zoomBehaviorRef = useRef(null);
    useEffect(() => {
        if (!treeData || levels.length === 0 || !svgRef.current) return;
        const svgEl = svgRef.current;
        const container = svgEl.parentElement;
        // Create or select tooltip (same style as GraphHEB)
        let tooltip = d3.select(container).select('.tooltip');
        if (tooltip.empty()) {
            tooltip = d3.select(container)
                .append('div')
                .attr('class', 'tooltip')
                .style('position', 'absolute')
                .style('opacity', 0)
                .style('background', 'rgba(255,255,255,0.98)')
                .style('color', '#333')
                .style('padding', '0')
                .style('border', '1px solid rgba(0,0,0,0.1)')
                .style('border-radius', '12px')
                .style('backdrop-filter', 'blur(20px)')
                .style('box-shadow', '0 12px 40px rgba(0,0,0,0.15)')
                .style('font-family', "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif")
                .style('font-size', '12px')
                .style('max-width', '350px')
                .style('line-height', '1.5')
                .style('overflow', 'hidden')
                .style('pointer-events', 'auto')
                .style('z-index', 12)
                .style('transition', 'opacity 0.15s');
        }
        // Close button HTML for tooltips
        const closeBtn = `<button onclick="this.closest('.tooltip').style.opacity='0';this.closest('.tooltip').style.pointerEvents='none'" style="position:absolute;top:6px;right:8px;background:none;border:none;color:white;font-size:16px;cursor:pointer;line-height:1;padding:0 2px;opacity:0.85;">&times;</button>`;
        // Track active tooltip target
        let activeTooltipTarget = null;
    // Dynamic sizing: keep fixed height but allow width to grow based on widest level
    const forcedHeight = 678;
    const paddingX = 60;
    const paddingY = 60;
    const baseGap = 40; // minimum gap between nodes
    // Precompute per-level required width (without compression)
    const levelMetrics = levels.map(levelNodes => {
        const nodeWidths = levelNodes.map(n => {
            const label = n.name || n.elementId;
            const estLabelWidth = Math.min(140, (label.length * 7)) + 12; // match rect logic
            const circleDiameter = 36; // r=18
            return Math.max(circleDiameter, estLabelWidth);
        });
        const totalNeeded = nodeWidths.reduce((a,b)=>a+b,0) + baseGap * Math.max(0, nodeWidths.length -1);
        return { nodeWidths, totalNeeded };
    });
    const widest = levelMetrics.reduce((m,l)=> Math.max(m, l.totalNeeded), 0);
    const containerWidth = Math.max(678, Math.min(2400, widest + paddingX * 2));
    const containerHeight = forcedHeight;
        const svg = d3.select(svgEl);
    // Click on empty SVG background dismisses any open tooltip
    svg.on('click', function(event) {
      if (event.target === svgEl) {
        tooltip.style('opacity', 0).style('pointer-events', 'none');
        activeTooltipTarget = null;
      }
    });
    svg.selectAll('*').remove();
        // Define arrowhead markers
        const defs = svg.append('defs');
        const baseArrow = defs.append('marker')
            .attr('id','hier-arrow')
            .attr('viewBox','0 0 10 10')
            // refX tuned so the arrow tip sits just outside the target node edge after we shorten the link
            .attr('refX',9)
            .attr('refY',5)
            .attr('markerWidth',7)
            .attr('markerHeight',7)
            .attr('orient','auto');
        baseArrow.append('path').attr('d','M0,0 L10,5 L0,10 Z').attr('fill','#999');
        const activeArrow = defs.append('marker')
            .attr('id','hier-arrow-active')
            .attr('viewBox','0 0 10 10')
            .attr('refX',9)
            .attr('refY',5)
            .attr('markerWidth',8)
            .attr('markerHeight',8)
            .attr('orient','auto');
        activeArrow.append('path').attr('d','M0,0 L10,5 L0,10 Z').attr('fill','#ff9800');
    // Use containerWidth directly as logical width
    const width = containerWidth - 20;
    const levelHeight = 160; // vertical spacing
    svg.attr('width', containerWidth).attr('height', containerHeight);

        // Position nodes: levels[0] is top ancestors, last level contains selected node
        const positionedNodes = [];
        levels.forEach((levelNodes, idx) => {
            const y = paddingY + idx * levelHeight;
            const metrics = levelMetrics[idx];
            const nodeWidths = metrics.nodeWidths;
            const totalNeeded = metrics.totalNeeded;
            // No compression; allow horizontal scroll if exceeds viewport
            let cursorX = paddingX + (width - (totalNeeded)) / 2;
            // If totalNeeded > width, cursorX starts at paddingX (left aligned) for clarity
            if (totalNeeded > width) cursorX = paddingX;
            levelNodes.forEach((n,i)=> {
                const w = nodeWidths[i];
                const xCenter = cursorX + w/2;
                positionedNodes.push({ ...n, x: xCenter, y });
                cursorX += w + baseGap;
            });
        });
        const nodePosMap = new Map(positionedNodes.map(n => [n.elementId, n]));

        // Root group for zooming
        const g = svg.append('g').attr('class','zoom-layer');
        const links = treeData.links;

        // --- Arrowhead visibility adjustment for bidirectional (two-way) relationships ---
        // Goal: If two nodes have links in both directions, only show ONE arrowhead pointing "upward" (towards the ancestor).
        // Ancestor detection: nodes at higher index distance (farther from selected node) appear in earlier levels array.
        // Distance heuristic: derive distance-from-selected (0 = selected/root of this view) by reversing level ordering.
        const distanceMap = new Map();
        levels.forEach((levelNodes, idx) => {
            // levels[0] = farthest ancestors, last = selected node; compute original distance
            const distanceFromSelected = (levels.length - 1) - idx; // so selected node distance 0
            levelNodes.forEach(n => distanceMap.set(n.elementId, distanceFromSelected));
        });

        // Build per-pair direction map
        const pairDirMap = new Map(); // key: sorted pair id, value: array of link refs
        links.forEach(l => {
            if (!nodePosMap.has(l.source) || !nodePosMap.has(l.target)) return; // skip orphan
            const a = l.source;
            const b = l.target;
            const pairKey = a < b ? `${a}|${b}` : `${b}|${a}`;
            if (!pairDirMap.has(pairKey)) pairDirMap.set(pairKey, []);
            pairDirMap.get(pairKey).push(l);
        });

        // Default: every link shows arrowhead unless suppressed below
        links.forEach(l => { l.__showArrow = true; });

        pairDirMap.forEach(linkArr => {
            if (linkArr.length < 2) return; // only one direction, leave as-is
            // If more than 2 (multiple relationship types both ways) treat all by direction groups
            // Group by direction signature source->target vs target->source using the first pair encountered.
            // Determine which direction is upward: the one whose TARGET has greater distance (farther from selected / higher in hierarchy)
            // Because links are stored parent->child normally, the reverse (child->parent) is the upward one.
            linkArr.forEach(l => { l.__showArrow = false; }); // start by clearing all then enable one
            let chosen = null;
            linkArr.forEach(l => {
                const srcDist = distanceMap.get(l.source);
                const tgtDist = distanceMap.get(l.target);
                if (srcDist == null || tgtDist == null) return; // safety
                // Upward if target is farther from selected (higher ancestor) i.e., tgtDist > srcDist
                if (tgtDist > srcDist) {
                    if (!chosen) chosen = l; // first qualifying upward link
                }
            });
            // Fallback: if none matched (e.g., equal distances due to data anomaly), pick arbitrary stable link
            if (!chosen && linkArr.length) chosen = linkArr[0];
            if (chosen) chosen.__showArrow = true;
        });

        g.selectAll('.link')
            .data(links.filter(l => nodePosMap.has(l.source) && nodePosMap.has(l.target)))
            .enter()
            .append('path')
            .attr('class', 'link')
            .attr('d', d => {
                // Shorten the line at both ends so the arrowhead sits just outside node icon/circle
                const s = nodePosMap.get(d.source);
                const t = nodePosMap.get(d.target);
                if (!s || !t) return '';
                const dx = t.x - s.x;
                const dy = t.y - s.y;
                const len = Math.sqrt(dx*dx + dy*dy) || 1;
                // Base visual radius of node (icon 36px -> radius 18) + small padding to keep arrowhead off the node
                const rSource = 18; // could vary if different node sizes later
                const rTarget = 18;
                // Additional padding so arrowhead tip touches the node edge not hidden beneath
                const padTarget = 4; // tweak as needed
                const padSource = 4;
                const ux = dx / len;
                const uy = dy / len;
                const startX = s.x + ux * (rSource + padSource);
                const startY = s.y + uy * (rSource + padSource);
                const endX = t.x - ux * (rTarget + padTarget);
                const endY = t.y - uy * (rTarget + padTarget);
                return `M${startX},${startY} L${endX},${endY}`;
            })
            .attr('fill', 'none')
            .attr('stroke', '#999')
            .attr('stroke-width', 2)
            .attr('stroke-opacity', 0.9)
            .attr('marker-end', d => d.__showArrow ? 'url(#hier-arrow)' : null)
            // Ensure links render above background and below nodes but arrowhead remains visible (shortened path)
            .style('pointer-events','stroke')
            .on('click', function(event, d) {
                event.stopPropagation();
                const linkId = d.elementId || `${d.source}-${d.target}`;
                if (activeTooltipTarget && activeTooltipTarget !== linkId) {
                    tooltip.style('opacity', 0).style('pointer-events', 'none');
                }
                activeTooltipTarget = linkId;

                d3.select(this)
                    .attr('stroke','#ff9800')
                    .attr('stroke-width',3)
                    .attr('marker-end', d.__showArrow ? 'url(#hier-arrow-active)' : null);
                
                const relType = d.type || 'Relationship';
                const props = d.properties && typeof d.properties === 'object' && !Array.isArray(d.properties) 
                  ? d.properties 
                  : d;
                
                const sourceNode = nodePosMap.get(d.source);
                const targetNode = nodePosMap.get(d.target);
                const srcLabel = sourceNode?.labels?.[0] || 'Node';
                const tgtLabel = targetNode?.labels?.[0] || 'Node';
                
                let tooltipContent = `
                  <div style="position:relative; background: linear-gradient(135deg, #ff6b6b 0%, #feca57 100%); color: white; padding: 8px 12px; margin: -8px -8px 8px -8px; font-weight: bold; border-radius: 4px 4px 0 0;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <i class="fas fa-link" style="font-size: 16px;"></i>
                      <span>${relType}</span>
                    </div>
                    ${closeBtn}
                  </div>
                `;
                
                tooltipContent += `<div style="margin: 8px; padding: 8px; background: #f8f9fa; border-radius: 4px; font-size: 11px; color: #495057;">
                  <strong style="color: #0066B3;">From:</strong> ${srcLabel}<br/>
                  <strong style="color: #28A745;">To:</strong> ${tgtLabel}
                </div>`;
                
                // Only exclude D3/graph-library internals — ALL real relationship properties will be shown
                const excludedProps = [
                  'source', 'target', 'index',                                           // D3 link internals
                  'start', 'end',                                                        // Neo4j relationship endpoints
                  'elementId', 'elementID', 'identity', 'properties', '__typename',       // driver metadata
                  '__showArrow',                                                          // custom display flag
                ];
                
                const allProps = Object.keys(props)
                  .filter(k => {
                    if (excludedProps.includes(k)) return false;
                    if (typeof props[k] === 'function') return false;
                    return true;
                  })
                  .map(k => [k, props[k]]);
                
                if (allProps.length > 0) {
                  tooltipContent += `<div style="margin-top: 8px; padding: 8px; font-size: 12px; max-height: 250px; overflow-y: auto;">`;
                  allProps.forEach(([k, v]) => {
                    const formattedKey = k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    let formattedValue = v;
                    if (v === null || v === undefined) {
                      formattedValue = '<em style="color: #95a5a6;">N/A</em>';
                    } else if (typeof v === 'object') {
                      formattedValue = JSON.stringify(v);
                    } else if (typeof v === 'boolean') {
                      formattedValue = v ? '<span style="color: #27ae60;">Yes</span>' : '<span style="color: #e74c3c;">No</span>';
                    } else {
                      formattedValue = String(v);
                    }
                    tooltipContent += `<div style="margin: 4px 0; padding: 3px 0; border-bottom: 1px solid #f0f0f0;"><strong style="color: #2c3e50;">${formattedKey}:</strong> <span style="color: #34495e; margin-left: 8px;">${formattedValue}</span></div>`;
                  });
                  tooltipContent += `</div>`;
                } else {
                  tooltipContent += `<div style="margin-top: 8px; padding: 12px; font-size: 12px; color: #95a5a6; font-style: italic; text-align: center;">No properties available</div>`;
                }
                
                tooltip.html(tooltipContent)
                    .style('left', (event.offsetX + 14) + 'px')
                    .style('top', (event.offsetY + 14) + 'px')
                    .style('pointer-events', 'auto')
                    .style('opacity', 1);
            });

        // Draw nodes
        // Deduplicate duplicates while ensuring we KEEP the selected/root node at its correct (lowest) level.
        // Previous logic kept the first occurrence (top-level) which was wrong when the root appeared twice.
        const rootId = treeData.root.elementId;
        let rootMaxY = -Infinity;
        positionedNodes.forEach(pn => {
            if (pn.elementId === rootId && pn.y > rootMaxY) rootMaxY = pn.y; // find lowest (largest y) root occurrence
        });
        const uniquePositioned = [];
        const seenIds = new Set();
        // We want to keep last occurrence for any duplicate IDs so iterate from end to start.
        for (let i = positionedNodes.length - 1; i >= 0; i--) {
            const pn = positionedNodes[i];
            // For root node keep only the one at rootMaxY
            if (pn.elementId === rootId && pn.y !== rootMaxY) continue;
            if (!seenIds.has(pn.elementId)) {
                seenIds.add(pn.elementId);
                // We'll push in reverse order then reverse later to restore drawing order (top ancestors first)
                uniquePositioned.push(pn);
            }
        }
        uniquePositioned.reverse();
        const nodeGroup = g.selectAll('.node')
            .data(uniquePositioned)
            .enter()
            .append('g')
            .attr('class', 'node')
            .attr('transform', d => `translate(${d.x},${d.y})`);

        // Draw icon or fallback circle
        nodeGroup.each(function(d) {
            const gnode = d3.select(this);
            const primaryLabel = d.labels?.[0] || d.label || 'Unknown';
            const nodeColor = getNodeColor(primaryLabel);
            
            // Use colored circles instead of icons
            gnode.append('circle')
                .attr('r', 18)
                .attr('fill', d.elementId === treeData.root.elementId ? '#ff6b6b' : nodeColor)
                .attr('stroke', '#fff')
                .attr('stroke-width', 2)
                .attr('filter', 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))');
        });

        // Add label group below circle to avoid overlap with node center
    // Move label further down so it doesn't overlap circle edge
    const labelGroup = nodeGroup.append('g').attr('transform', 'translate(0,40)');
        // Draw background rect first; final sizing will be adjusted after wrapping
        labelGroup.append('rect')
            .attr('x', -60)
            .attr('y', -10)
            .attr('height', 32)
            .attr('width', 120)
            .attr('rx', 4)
            .attr('ry', 4)
            .attr('fill', 'rgba(255,255,255,0.85)')
            .attr('stroke', '#ddd');

        // Multi-line wrapping for labels
        labelGroup.each(function(d) {
            // Developer-configured property with configurable priority (see DISPLAY_NAME_PROPERTY / DISPLAY_MODE at top of file)
            const props = d.properties || d;
            const nodeLabel = d.labels?.[0] || d.label || '';
            let propValue = resolveDisplayProp(props);
            if (!propValue) {
                propValue = schemaDisplayName ? schemaDisplayName(d) : (
                    props.name || props.title || props.code || props.key ||
                    props.abbreviation || props.milestone_abbreviation ||
                    props.jira_project_key || props.project_name ||
                    props.milestone_name || props.workproduct_name ||
                    d.elementId || ''
                );
            }
            const displayText = formatNodeDisplay(nodeLabel, propValue);
            const maxCharsPerLine = 18; // heuristic per line
            const words = displayText.split(/[\s_-]+/).filter(Boolean);
            const lines = [];
            let current = '';
            words.forEach(w => {
                const test = current ? current + ' ' + w : w;
                if (test.length <= maxCharsPerLine) {
                    current = test;
                } else {
                    if (current) lines.push(current);
                    current = w;
                }
            });
            if (current) lines.push(current);
            // Fallback if no words (e.g., single long token)
            if (lines.length === 0 && displayText) {
                for (let i = 0; i < displayText.length; i += maxCharsPerLine) {
                    lines.push(displayText.slice(i, i + maxCharsPerLine));
                }
            }
            const lineHeight = 14;
            const maxLineLen = Math.max(...lines.map(l => l.length), 0);
            const approxWidth = Math.min(160, maxLineLen * 7) + 16; // padding
            const totalHeight = lineHeight * lines.length + 8; // padding
            // Adjust rectangle size & position
            d3.select(this).select('rect')
                .attr('width', approxWidth)
                .attr('x', -approxWidth / 2)
                .attr('height', totalHeight)
                .attr('y', -totalHeight / 2);
            // Append text with tspans
            const textEl = d3.select(this).append('text')
                .attr('class', 'hier-node-label')
                .attr('text-anchor', 'middle')
                .attr('fill', '#000')
                .style('font-size', '12px')
                .style('font-weight', '500')
                .style('pointer-events', 'none');
            lines.forEach((line, i) => {
                textEl.append('tspan')
                    .attr('x', 0)
                    .attr('dy', i === 0 ? (lines.length === 1 ? lineHeight/2 : 0) : lineHeight)
                    .text(line);
            });
            // Center first line vertically when single line
            if (lines.length === 1) {
                textEl.attr('dy', lineHeight/2);
            }
        });

        // Attach unified hover handlers to entire node group (circle + label)
        nodeGroup
            .on('click', function(event, d) {
                event.stopPropagation();
                const nodeId = d.elementId || d.id;
                if (activeTooltipTarget && activeTooltipTarget !== nodeId) {
                    tooltip.style('opacity', 0).style('pointer-events', 'none');
                }
                activeTooltipTarget = nodeId;

                d3.select(this).select('circle').attr('stroke', '#222').attr('stroke-width', 3);
                
                const nodeType = d.labels?.[0] || 'Node';
                const props = d.properties && typeof d.properties === 'object' && !Array.isArray(d.properties) 
                  ? d.properties 
                  : d;
                
                                let tooltipContent = buildTooltipHeader(nodeType, closeBtn);
                
                                // Show all enumerable own properties (exclude functions only)
                                const allProps = Object.keys(props)
                                    .filter(k => typeof props[k] !== 'function')
                                    .map(k => [k, props[k]]);
                
                if (allProps.length > 0) {
                  tooltipContent += `<div style="margin-top: 8px; padding: 8px; font-size: 12px; max-height: 300px; overflow-y: auto;">`;
                  allProps.forEach(([k, v]) => {
                    const formattedKey = k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    let formattedValue = v;
                    if (v === null || v === undefined) {
                      formattedValue = '<em style="color: #95a5a6;">N/A</em>';
                    } else if (typeof v === 'object') {
                      formattedValue = JSON.stringify(v);
                    } else if (typeof v === 'boolean') {
                      formattedValue = v ? '<span style="color: #27ae60;">Yes</span>' : '<span style="color: #e74c3c;">No</span>';
                    } else {
                      formattedValue = String(v);
                    }
                    tooltipContent += `<div style="margin: 4px 0; padding: 3px 0; border-bottom: 1px solid #f0f0f0;"><strong style="color: #2c3e50;">${formattedKey}:</strong> <span style="color: #34495e; margin-left: 8px;">${formattedValue}</span></div>`;
                  });
                  tooltipContent += `</div>`;
                } else {
                  tooltipContent += `<div style="margin-top: 8px; padding: 8px; font-size: 12px; color: #95a5a6; font-style: italic;">No properties available</div>`;
                }
                
                // Dock tooltip to right side of the SVG canvas
                const svgRect = svgEl.getBoundingClientRect();
                const parentRect = container.getBoundingClientRect();
                const panelWidth = 340;
                let panelTop = Math.max(0, Math.round(svgRect.top - parentRect.top));
                let panelLeft = Math.max(0, Math.round(svgRect.right - parentRect.left - panelWidth));
                if (svgRect.width < panelWidth) panelLeft = Math.max(0, Math.round(svgRect.left - parentRect.left));
                tooltip.html(tooltipContent)
                    .style('left', panelLeft + 'px')
                    .style('top', panelTop + 'px')
                    .style('pointer-events', 'auto')
                    .style('opacity', 1)
                    .style('width', panelWidth + 'px')
                    .style('max-height', Math.min(svgRect.height, window.innerHeight - 40) + 'px')
                    .style('overflow-y', 'auto');
            });

        // Compute bounding box of logical content for auto-fit
        const xs = positionedNodes.map(n => n.x);
        const ys = positionedNodes.map(n => n.y);
        const minX = Math.min(...xs) - 40;
        const maxX = Math.max(...xs) + 40;
        const minY = Math.min(...ys) - 40;
        const maxY = Math.max(...ys) + 40;
        const contentWidth = maxX - minX;
        const contentHeight = maxY - minY;
        const scale = Math.min(
            containerWidth / contentWidth,
            containerHeight / contentHeight,
            1 // avoid upscaling beyond 1
        );
        const offsetX = (containerWidth - contentWidth * scale) / 2 - minX * scale;
        const offsetY = (containerHeight - contentHeight * scale) / 2 - minY * scale;
        g.attr('transform', `translate(${offsetX},${offsetY}) scale(${scale})`);

        // Define zoom behavior
        zoomBehaviorRef.current = d3.zoom()
            .scaleExtent([0.2, 2])
            .on('zoom', (event) => {
                g.attr('transform', event.transform);
            });
        svg.call(zoomBehaviorRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [treeData, levels]);

    const getNodeDisplayName = (node) => {
        if (!node) return 'Unknown';
        const firstLabel = node.labels?.[0] || node.label || 'Unknown';
        const props = node.properties || node;

        // Resolve property from priority list (see DISPLAY_NAME_PROPERTY at top of file)
        let propValue = resolveDisplayProp(props);

        if (!propValue) {
            // Schema-driven fallback
            if (schemaDisplayName) propValue = schemaDisplayName(node);
        }

        if (!propValue) {
            // Heuristic fallback
            propValue = props.name || props.title || props.code || props.key ||
                        props.abbreviation || props.jira_project_key ||
                        props.project_name || props.milestone_name ||
                        props.milestone_abbreviation || props.workproduct_name ||
                        'Unnamed';
        }

        return formatNodeDisplay(firstLabel, propValue);
    };

    return (
        <div style={{ padding: '12px 20px', boxSizing: 'border-box', overflow: 'hidden', display:'flex', flexDirection:'column', flex:1, minHeight:0 }}>
            {/* Duplicate header & back button removed; toolbar provided by parent App.js */}
            <p style={{ marginTop:0, marginBottom: '12px' }}>Search for a node to see all parent hierarchies leading to it</p>

            {/* Search Section */}
            <div style={{ marginBottom: '20px', display: 'flex', gap: '10px', alignItems: 'center' }}>
                <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Search for a node..."
                    style={{ 
                        padding: '8px 12px', 
                        border: '1px solid #ddd', 
                        borderRadius: '4px',
                        width: '300px'
                    }}
                    onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                />
                <button 
                    onClick={handleSearch}
                    disabled={isSearching}
                    style={{
                        padding: '8px 16px',
                        backgroundColor: isSearching ? 'rgba(10,130,118,0.6)' : primaryButtonColor,
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: isSearching ? 'not-allowed' : 'pointer'
                    }}
                >
                    {isSearching ? 'Searching...' : 'Search'}
                </button>
                {searchError && (
                    <span style={{ color: '#a94442', fontSize: 12 }}>{searchError}</span>
                )}
            </div>
            {/* Search Results */}
            {hierarchySearchResults.length > 0 && (
                <div style={{ marginBottom: '20px' }}>
                    <h4 style={{ margin: '0 0 10px 0', fontSize: 14, color: '#2c3e50' }}>Search Results ({hierarchySearchResults.length})</h4>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', maxHeight: '200px', overflowY: 'auto', padding: '4px' }}>
                        {hierarchySearchResults.map((node) => {
                            const nodeLabel = node.labels?.[0] || node.label || 'Node';
                            const isSelected = selectedNode?.elementId === node.elementId;
                            const displayName = (() => {
                                const props = node.properties || node;
                                let val = resolveDisplayProp(props);
                                if (!val) val = schemaDisplayName ? schemaDisplayName(node) : (props.name || props.title || props.code || props.key || props.abbreviation || 'Unnamed');
                                return formatNodeDisplay(nodeLabel, val);
                            })();
                            return (
                                <div
                                    key={node.elementId}
                                    onClick={() => handleNodeSelect(node)}
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '8px',
                                        padding: '8px 12px',
                                        backgroundColor: isSelected ? primaryButtonColor : '#fff',
                                        color: isSelected ? 'white' : '#333',
                                        border: isSelected ? `2px solid ${primaryButtonColor}` : '1px solid #e0e0e0',
                                        borderRadius: '8px',
                                        cursor: 'pointer',
                                        transition: 'all 0.15s ease',
                                        boxShadow: isSelected ? '0 2px 8px rgba(10,130,118,0.3)' : '0 1px 3px rgba(0,0,0,0.08)',
                                        minWidth: '120px',
                                        maxWidth: '280px'
                                    }}
                                >
                                    <span style={{
                                        display: 'inline-block',
                                        padding: '2px 8px',
                                        borderRadius: '4px',
                                        fontSize: '10px',
                                        fontWeight: 600,
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.5px',
                                        backgroundColor: isSelected ? 'rgba(255,255,255,0.25)' : getNodeColor(nodeLabel),
                                        color: 'white',
                                        whiteSpace: 'nowrap',
                                        flexShrink: 0
                                    }}>{nodeLabel}</span>
                                    <span style={{
                                        fontSize: '13px',
                                        fontWeight: 500,
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap'
                                    }}>{displayName}</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Tree Visualization */}
            {treeData && (
                <div style={{ flex:1, display:'flex', flexDirection:'column', minHeight:0 }}>
                    <div style={{ display:'flex', alignItems:'center', gap:16, flexWrap:'wrap', marginBottom:8 }}>
                        <h4 style={{ margin:0 }}>Parent Hierarchy for: {getNodeDisplayName(selectedNode)}</h4>
                        <span style={{ fontSize: 12, color: '#555' }}>Levels: {levels.length} | Ancestors: {treeData.nodes.length - 1} | Links: {treeData.links.length}</span>
                        {isExpandingUpwards && <span style={{ color: '#0a8276', fontSize: 12 }}>Expanding...</span>}
                        {expansionError && <span style={{ color: '#a94442', fontSize: 12 }}>Error: {expansionError}</span>}
                        {!autoExpanded && !isExpandingUpwards && (
                            <button onClick={() => expandAllParents(selectedNode)} style={{ padding:'6px 12px', background: primaryButtonColor, color:'#fff', border:'none', borderRadius:4, cursor:'pointer' }}>Expand Upwards</button>
                        )}
                        <button onClick={() => {
                            // reset zoom to fit
                            if (svgRef.current) {
                                const svg = d3.select(svgRef.current);
                                svg.transition().duration(400).call(zoomBehaviorRef.current.transform, d3.zoomIdentity);
                            }
                        }} style={{ padding:'6px 12px', background: primaryButtonColor, color:'#fff', border:'none', borderRadius:4, cursor:'pointer' }}>Reset View</button>
                    </div>
                    <div style={{ position:'relative', flex:1, border:'1px solid #ddd', borderRadius:4, background:'#fafafa', overflow:'hidden' }}>
                        <svg ref={svgRef} style={{ display:'block', width:'100%', height:'100%' }}></svg>
                    </div>
                </div>
            )}

            {/* {selectedNode && !treeData?.parents?.length && (
                // <div style={{ marginTop: '20px', padding: '20px', backgroundColor: '#f8f9fa', borderRadius: '4px' }}>
                //     <p>No parent nodes found for <strong>{getNodeDisplayName(selectedNode)}</strong></p>
                //     <p>This appears to be a root level node.</p>
                // </div>
            )} */}
        </div>
    );
};

export default WhereUsedView;
