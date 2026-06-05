import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import * as d3 from 'd3';
import '../App.css';
import GraphHEB from './GraphHEB';

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
            const response = await axios.post('http://localhost:8000/graphfilter', { search: term.toLowerCase() });
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
            console.error('Search error (server):', err);
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
                    const resp = await axios.get(`http://localhost:8000/graphtraverse/${currentNode.elementId}`);
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
                    console.warn('Traverse fetch failed for', currentNode.elementId, e.message);
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
    // Zoom behavior defined outside effect (hoisted via ref) for reset button
    let zoomBehavior = null;
    useEffect(() => {
        if (!treeData || levels.length === 0 || !svgRef.current) return;
        const svgEl = svgRef.current;
        const container = svgEl.parentElement;
        // Create or select tooltip
        let tooltip = d3.select(container).select('.hier-tooltip');
        if (tooltip.empty()) {
            tooltip = d3.select(container)
                .append('div')
                .attr('class', 'hier-tooltip')
                .style('position', 'absolute')
                .style('padding', '6px 10px')
                .style('background', 'rgba(0,0,0,0.75)')
                .style('color', '#fff')
                .style('font-size', '12px')
                .style('border-radius', '4px')
                .style('pointer-events', 'none')
                .style('opacity', 0)
                .style('transition', 'opacity 0.15s');
        }
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
    const logicalHeight = paddingY * 2 + levelHeight * (levels.length - 1);
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
            .on('mouseover', function(event, d) {
                d3.select(this)
                    .attr('stroke','#ff9800')
                    .attr('stroke-width',3)
                    .attr('marker-end', d.__showArrow ? 'url(#hier-arrow-active)' : null);
                const relType = d.type || 'RELATIONSHIP';
                const sourceNode = nodePosMap.get(d.source);
                const targetNode = nodePosMap.get(d.target);
                const resolveName = (n) => {
                    if (!n) return 'Unknown';
                    // Generic property lookup
                    return n.name || 
                           n.title || 
                           n.code || 
                           n.key || 
                           n.abbreviation ||
                           n.jira_project_key ||
                           n.project_name || 
                           n.milestone_name || 
                           n.milestone_abbreviation ||
                           n.workproduct_name || 
                           'Unknown';
                };
                tooltip.html(`<strong>${relType}</strong><br/>Parent: ${resolveName(sourceNode)}<br/>Child: ${resolveName(targetNode)}<br/>ID: ${d.elementId}`)
                    .style('left', (event.offsetX + 14) + 'px')
                    .style('top', (event.offsetY + 14) + 'px')
                    .style('opacity', 1);
            })
            .on('mousemove', function(event) {
                tooltip
                    .style('left', (event.offsetX + 14) + 'px')
                    .style('top', (event.offsetY + 14) + 'px');
            })
            .on('mouseout', function() {
                d3.select(this)
                    .attr('stroke','#999')
                    .attr('stroke-width',2)
                    .attr('marker-end', d => d.__showArrow ? 'url(#hier-arrow)' : null);
                tooltip.style('opacity',0);
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
            const firstLabel = d.labels?.[0] || d.label || 'Unknown';
            // Generic property lookup
            const raw = d.name || 
                       d.title || 
                       d.code || 
                       d.key || 
                       d.abbreviation ||
                       d.milestone_abbreviation ||
                       d.jira_project_key ||
                       d.project_name || 
                       d.milestone_name || 
                       d.workproduct_name || 
                       d.elementId || 
                       '';
            const maxCharsPerLine = 18; // heuristic per line
            const words = raw.split(/[\s_-]+/).filter(Boolean);
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
            if (lines.length === 0 && raw) {
                for (let i = 0; i < raw.length; i += maxCharsPerLine) {
                    lines.push(raw.slice(i, i + maxCharsPerLine));
                }
            }
            const lineHeight = 14;
            const maxLineLen = Math.max(...lines.map(l => l.length), 0);
            const approxWidth = Math.min(160, maxLineLen * 7) + 16; // padding
            const totalHeight = lineHeight * lines.length + 8; // padding
            // Adjust rectangle size & position
            const rect = d3.select(this).select('rect')
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
            .on('mouseover', function(event, d) {
                // Only highlight the hovered node itself (no link highlighting)
                d3.select(this).select('circle').attr('stroke', '#222').attr('stroke-width', 3);
                // Build tooltip (still list relationship types, but purely informational)
                const connectedLinks = links.filter(l => l.source === d.elementId || l.target === d.elementId);
                const type = d.labels?.[0] || d.label || 'Node';
                // Generic property lookup
                const label = d.name || 
                             d.title || 
                             d.code || 
                             d.key || 
                             d.abbreviation ||
                             d.jira_project_key ||
                             d.project_name || 
                             d.milestone_name || 
                             d.milestone_abbreviation ||
                             d.workproduct_name || 
                             'Unnamed';
                const version = d.external_version || d.version || '';
                const relTypes = Array.from(new Set(connectedLinks.map(cl => cl.type).filter(Boolean)));
                const relHtml = relTypes.length ? `<br/>Relationships: ${relTypes.join(', ')}` : '<br/>Relationships: none';
                tooltip.html(`<strong>${label}</strong><br/>Type: ${type}${version ? `<br/>Version: ${version}` : ''}${relHtml}<br/>ID: ${d.elementId}`)
                    .style('left', (event.offsetX + 14) + 'px')
                    .style('top', (event.offsetY + 14) + 'px')
                    .style('opacity', 1);
            })
            .on('mousemove', function(event) {
                tooltip
                    .style('left', (event.offsetX + 14) + 'px')
                    .style('top', (event.offsetY + 14) + 'px');
            })
            .on('mouseout', function() {
                // Reset only hovered node circle stroke (leave links untouched)
                d3.select(this).select('circle')
                    .attr('stroke','#fff')
                    .attr('stroke-width',2);
                tooltip.style('opacity',0);
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
        zoomBehavior = d3.zoom()
            .scaleExtent([0.2, 2])
            .on('zoom', (event) => {
                g.attr('transform', event.transform);
            });
        svg.call(zoomBehavior);
    }, [treeData, levels]);

    const getNodeDisplayName = (node) => {
        if (!node) return 'Unknown';
        const firstLabel = node.labels?.[0] || node.label || 'Unknown';
        // Generic property lookup
        const name = node.name || 
                     node.title || 
                     node.code || 
                     node.key || 
                     node.abbreviation ||
                     node.jira_project_key ||
                     node.project_name || 
                     node.milestone_name || 
                     node.milestone_abbreviation ||
                     node.workproduct_name || 
                     'Unnamed';
        return `${name} (${firstLabel})`;
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
                    <h4>Search Results:</h4>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                        {hierarchySearchResults.map((node) => (
                            <button
                                key={node.elementId}
                                onClick={() => handleNodeSelect(node)}
                                style={{
                                    padding: '8px 12px',
                                    backgroundColor: selectedNode?.elementId === node.elementId ? primaryButtonColor : '#f8f9fa',
                                    color: selectedNode?.elementId === node.elementId ? 'white' : '#333',
                                    border: '1px solid #ddd',
                                    borderRadius: '4px',
                                    cursor: 'pointer',
                                    transition: 'background-color 0.15s'
                                }}
                            >
                                {getNodeDisplayName(node)}
                            </button>
                        ))}
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
                                svg.transition().duration(400).call(zoomBehavior.transform, d3.zoomIdentity);
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
