import {fitGraphViewport} from '../graphViewport';
import { useEffect } from 'react';
import * as d3 from "d3";
import { logger } from "../../../utils/logger";
import { getLinkEndpointId } from "../../../utils/graphUtils";
import { buildTooltipHeader } from "../../../Components/tooltipBuilder";
import { getNodeLabelStyle, getRelationshipLabelStyle, shouldRenderNodeLabels, shouldRenderRelationshipLabels, truncateGraphLabel } from "../../../utils/graphDisplayPolicy";
import { reconcileSimulationNodes, graphTopologyKey } from "../../../utils/graphInteractionState";
import { RELATIONSHIP_THEME, ARROW_HEAD_WIDTH, ARROW_HEAD_LENGTH, ARROW_REF_X, TCS_GRAPH_THEME, getAdaptiveLinkDistance, getAdaptiveChargeStrength, CENTER_FORCE_STRENGTH, getClusterTarget, getNodeSemanticFamily, getNodeCollisionRadius, getRelationshipVisual, getVisibleRelationshipOpacity, getVisibleRelationshipStrokeWidth, getRelationshipDisplayName, resolveNodeName, resolveNodeType, escapeHtml, CHAR_CHECK, CHAR_CROSS, NODE_RADIUS, EXPAND_CIRCLE_RADIUS, EXPAND_SYMBOL_SIZE, CHAR_MINUS, performanceLog, performanceWarn } from "../graphRenderingPolicy";

// Rendering owns simulation ticks and DOM listeners, never shared business records.
export default function useGraphSimulation({ model, runtime, actions, svgRef }) {
const { filteredData, graphSearchActive, activeDisplayData, graphViewMode, graphData, activeSearchResultId, loadingNodes, debouncedSearchQuery, activeGraphDataset, searchResultData, selectedOntology } = model;
const { gRef, zoomBehaviorRef, simulationRef, simulationLayoutRef, activeTooltipNodeRef, tooltipRef, highlightedNodeIdsRef, expandedNodesRef, nodeExpansionsRef, tickFrameRef, lastCenteredSearchRef, userInteractedWithGraphRef } = runtime;
const { onInspectNode, hideAllTooltips, handleZoom, initializeNodePositions, processLinksForOffset, boundaryForce, calculateCurvedPath, tooltipCloseBtn, getCurrentGraphSlice, applyTooltipCloseHandler, wireTooltipRecButtons, openTooltipRecommendation, repositionTooltip, getRelationshipLabelColor, dragstarted, dragged, dragended, getNodeColor, getPrimaryNodeLabel, getNodeLabelColor, canCollapseNode, hasExpandableConnections, collapseNode, expandNode, buildRecActionBar } = actions;
useEffect(() => {
    const startTime = performance.now();
    logger.render(`[RENDER] Starting render with ${filteredData.nodes?.length || 0} nodes, ${filteredData.links?.length || 0} links`);
    const svgElement = svgRef.current;
    if (!svgElement) {
      logger.warn('SVG ref is not available yet.');
      return undefined;
    }

    let layoutChanged = false;

    const svg = d3.select(svgElement);
    const width = model.viewport?.width || svgElement.clientWidth || 800;
    const height = model.viewport?.height || svgElement.clientHeight || 600;

    // Click on empty SVG background dismisses any open tooltip
    svg.on('click.graph-background', function(event) {
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
    const sourceRenderData = graphSearchActive
      ? (activeDisplayData.nodes.length > 0 ? activeDisplayData : { nodes: [], links: [] })
      : (graphViewMode === 'individual'
        ? (activeDisplayData.nodes.length > 0 ? activeDisplayData : { nodes: [], links: [] })
        : (activeDisplayData.nodes.length > 0 ? activeDisplayData :
            (graphData.nodes && graphData.nodes.length > 0) ? graphData :
            { nodes: [], links: [] }));
    const renderData = { ...sourceRenderData, nodes: reconcileSimulationNodes(sourceRenderData.nodes, simulationRef.current?.nodes() || []) };
    const nodeCount = renderData.nodes.length;

    if (!hasData) {
      svg.selectAll('.node-count-display').remove();
      if (gRef.current) {
        gRef.current.selectAll('*').remove();  // Only clear graph content
      }
      if (simulationRef.current) {
        simulationRef.current.stop();
        simulationRef.current = null;
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

    // Force-directed layout
    // Clear graph content and ensure proper group structure
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
    const linkCount = processedLinks.length;
    const showNodeLabels = shouldRenderNodeLabels(nodeCount, linkCount, graphSearchActive, graphViewMode);
    const layoutKey = JSON.stringify([width, height, graphViewMode, showNodeLabels]);
    layoutChanged = simulationLayoutRef.current !== layoutKey;
    simulationLayoutRef.current = layoutKey;
    const nodeLabelStyle = { ...getNodeLabelStyle(nodeCount, graphViewMode) };
    if (!showNodeLabels) { nodeLabelStyle.fontSize = 11; nodeLabelStyle.maxLength = 48; }
    const labelVisible = d => showNodeLabels || d.elementId === activeSearchResultId || d.elementId === activeTooltipNodeRef.current || highlightedNodeIdsRef.current.has(d.elementId);
    const shouldClusterDenseGraph = graphViewMode === 'ontology' && !graphSearchActive && nodeCount > 140;
    const clusterStrength = shouldClusterDenseGraph ? 0.045 : 0.028;

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
          return getAdaptiveLinkDistance(relationshipType, nodeCount, linkCount);
        }))
        .force('charge', d3.forceManyBody().strength(getAdaptiveChargeStrength(nodeCount)))
        .force('center', d3.forceCenter(width / 2, height / 2).strength(CENTER_FORCE_STRENGTH))
        .force('x', d3.forceX((d) => (
          shouldClusterDenseGraph ? getClusterTarget(getNodeSemanticFamily(d), width, height).x : width / 2
        )).strength(clusterStrength))
        .force('y', d3.forceY((d) => (
          shouldClusterDenseGraph ? getClusterTarget(getNodeSemanticFamily(d), width, height).y : height / 2
        )).strength(shouldClusterDenseGraph ? 0.04 : 0.022))
        .force('collide', d3.forceCollide().radius((d) => getNodeCollisionRadius(d, showNodeLabels)).iterations(renderData.nodes.length > 300 ? 1 : 2))
        .force('boundary', boundaryForce(width, height));

      // Performance optimization: reduce iterations for large graphs
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
      const currentSimulationLinks = simulationRef.current.force('link')?.links?.() || [];
      const nodesChanged = JSON.stringify(currentNodes.map(node => node.elementId).sort())
        !== JSON.stringify(renderData.nodes.map(node => node.elementId).sort());
      const linksChanged = graphTopologyKey(currentNodes, currentSimulationLinks)
        !== graphTopologyKey(renderData.nodes, processedLinks);

      if (nodesChanged || linksChanged || layoutChanged) {
        // Update simulation data
        simulationRef.current.nodes(renderData.nodes);
        simulationRef.current.force('link').links(processedLinks);
        simulationRef.current.force('center', d3.forceCenter(width / 2, height / 2).strength(CENTER_FORCE_STRENGTH));
        simulationRef.current.force('x', d3.forceX((d) => (
          shouldClusterDenseGraph ? getClusterTarget(getNodeSemanticFamily(d), width, height).x : width / 2
        )).strength(clusterStrength));
        simulationRef.current.force('y', d3.forceY((d) => (
          shouldClusterDenseGraph ? getClusterTarget(getNodeSemanticFamily(d), width, height).y : height / 2
        )).strength(shouldClusterDenseGraph ? 0.04 : 0.022));
        simulationRef.current.force('charge', d3.forceManyBody().strength(getAdaptiveChargeStrength(nodeCount)));
        simulationRef.current.force('collide', d3.forceCollide().radius((d) => getNodeCollisionRadius(d, showNodeLabels)).iterations(renderData.nodes.length > 300 ? 1 : 2));
        simulationRef.current.force('boundary', boundaryForce(width, height));

        // Use lower alpha for smoother transitions, higher for layout changes
        const alpha = layoutChanged ? 0.5 : 0.3;
        simulationRef.current.alpha(alpha).restart();
        logger.render(`D3 Simulation updated with alpha ${alpha} (nodes changed: ${nodesChanged}, links changed: ${linksChanged}, layout changed: ${layoutChanged})`);
      } else {
        simulationRef.current.force('link').links(processedLinks);
        logger.render('Skipping simulation update - no data changes detected');
      }
    }

    const simulationLinks = simulationRef.current?.force('link')?.links?.() || processedLinks;
    const nodeById = new Map((renderData.nodes || []).map((node) => [node.elementId, node]));
    const resolveLinkNode = (endpoint) => {
      if (!endpoint) return null;
      if (typeof endpoint === 'object') {
        const endpointId = getLinkEndpointId(endpoint);
        return nodeById.get(endpointId) || endpoint;
      }
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
            .attr('stroke-opacity', getVisibleRelationshipOpacity(nodeCount, linkCount))
            .attr('stroke-width', d => getVisibleRelationshipStrokeWidth(d.type, nodeCount, linkCount))
            .attr('stroke-dasharray', d => getRelationshipVisual(d.type).dasharray)
            .attr('fill', 'none')  // Important for path elements
            .attr('marker-end', d => d.properties?.collapsed ? null : `url(#${getRelationshipVisual(d.type).markerId})`)
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
              let tooltipContent = buildTooltipHeader(relationshipType, tooltipCloseBtn, getRelationshipVisual(d.type).color);

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
                  tooltipRef.current.innerHTML = tooltipContent;
                  try { applyTooltipCloseHandler(tooltipRef.current); } catch (e) { /* ignore */ }
                  try { wireTooltipRecButtons(tooltipRef.current, openTooltipRecommendation); } catch (e) { /* ignore */ }
                  repositionTooltip();
              }
            })

          return group;
        },
        update => update,
        exit => exit.remove()
      );

    const relationshipLabelStyle = getRelationshipLabelStyle(simulationLinks.length, graphViewMode);
    const shouldShowRelationshipLabels = shouldRenderRelationshipLabels(nodeCount, simulationLinks.length, graphSearchActive, graphViewMode);
    const linkLabel = shouldShowRelationshipLabels
          ? gRef.current.selectAll('.link-label')
        .data(simulationLinks.filter((d) => d?.type), (d) => d.elementId)
        .join(
          (enter) => enter.append('text')
            .attr('class', 'link-label')
            .attr('font-size', relationshipLabelStyle.fontSize)
            .attr('font-weight', 600)
            .attr('text-anchor', 'middle')
            .attr('fill', d => getRelationshipLabelColor(d.type))
            .attr('paint-order', 'stroke fill')
            .attr('stroke', TCS_GRAPH_THEME.surface)
            .attr('stroke-width', 3)
            .attr('stroke-linejoin', 'round')
            .style('pointer-events', 'none')
            .text((d) => truncateGraphLabel(getRelationshipDisplayName(d), relationshipLabelStyle.maxLength)),
          (update) => update
            .attr('font-size', relationshipLabelStyle.fontSize)
            .attr('fill', d => getRelationshipLabelColor(d.type))
            .text((d) => truncateGraphLabel(getRelationshipDisplayName(d), relationshipLabelStyle.maxLength)),
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
            .attr('fill', d => getNodeColor(d))
            .attr('stroke', d => d3.color(getNodeColor(d))?.darker(0.9)?.formatHex?.() || TCS_GRAPH_THEME.borderStrong)
            .attr('stroke-width', 1.2);

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

          // Node label text (using unified logic)
          group.append('text')
            .attr('class', 'node-label')
            .text(d => labelVisible(d) ? truncateGraphLabel(getPrimaryNodeLabel(d), nodeLabelStyle.maxLength) : '')
            .attr('font-size', nodeLabelStyle.fontSize)
            .attr('font-weight', 'bold')
            .attr('dx', NODE_RADIUS + 5)
            .attr('dy', 3)
            .attr('fill', d => getNodeLabelColor(d))
            .style('display', d => labelVisible(d) ? null : 'none')
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
            onInspectNode?.(nodeId);
            gRef.current.selectAll('.node-label').style('display', item => labelVisible(item) ? null : 'none').text(item => labelVisible(item) ? truncateGraphLabel(getPrimaryNodeLabel(item), nodeLabelStyle.maxLength) : '');

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
            let tooltipContent = buildTooltipHeader(nodeType, tooltipCloseBtn, getNodeColor(d));
            // Recommendation action buttons (top, right after header)
            tooltipContent += buildRecActionBar(d);

            // Only exclude D3/graph-library internals ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ALL real knowledge graph properties will be shown
            const excludedProps = [
              'x', 'y', 'vx', 'vy', 'fx', 'fy', 'index',              // D3 force layout
              'depth', 'parent', 'data', 'height', 'level', 'children', // D3/internal hierarchy metadata
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
                  <strong style="color: #28A745;">ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¾ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢</strong> ${escapeHtml(propName)}
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
                const arrow = isOutgoing ? '->' : '<-';

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
              tooltipRef.current.innerHTML = tooltipContent;
              try { applyTooltipCloseHandler(tooltipRef.current); } catch (e) { /* ignore */ }
              try { wireTooltipRecButtons(tooltipRef.current, openTooltipRecommendation); } catch (e) { /* ignore */ }
              repositionTooltip();
            }
          })
          .on('mouseenter.context-label', function (event, d) {
            d3.select(this).raise().select('.node-label').style('display', null).text(truncateGraphLabel(getPrimaryNodeLabel(d), 64));
          })
          .on('mouseout', function (event, d) {
            d3.select(this).select('.node-label').style('display', labelVisible(d) ? null : 'none').text(labelVisible(d) ? truncateGraphLabel(getPrimaryNodeLabel(d), nodeLabelStyle.maxLength) : '');
            d3.select(this).select('.node-circle')
              .attr('stroke', null)
              .attr('stroke-width', null);
          });

          return group;
        },
        update => {
          // Update circle color based on label
          update.select('.node-circle')
            .attr('fill', d => getNodeColor(d))
            .attr('stroke', d => d3.color(getNodeColor(d))?.darker(0.9)?.formatHex?.() || TCS_GRAPH_THEME.borderStrong)
            .attr('stroke-width', 1.2);

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
            .text(d => labelVisible(d) ? truncateGraphLabel(getPrimaryNodeLabel(d), nodeLabelStyle.maxLength) : '')
            .attr('font-size', nodeLabelStyle.fontSize)
            .attr('font-weight', 'bold')
            .attr('fill', d => getNodeLabelColor(d))
            .style('display', d => labelVisible(d) ? null : 'none');

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

          update.select('.expand-control-hitbox')
            .style('pointer-events', d => (
              (hasExpandableConnections(d) || canCollapseNode(d)) ? 'all' : 'none'
            ))
            .style('cursor', d => (
              (hasExpandableConnections(d) || canCollapseNode(d)) ? 'pointer' : 'default'
            ));

          // Update loading indicator
          update.select('.loading-indicator')
            .style('opacity', d => loadingNodes.has(d.elementId) ? 1 : 0);

          return update;
        },
        exit => exit.remove()
      );

    link
      .attr('stroke', d => getRelationshipVisual(d.type).color)
      .attr('stroke-opacity', getVisibleRelationshipOpacity(nodeCount, linkCount))
      .attr('stroke-width', d => getVisibleRelationshipStrokeWidth(d.type, nodeCount, linkCount))
      .attr('stroke-dasharray', d => getRelationshipVisual(d.type).dasharray)
      .attr('marker-end', d => d.properties?.collapsed ? null : `url(#${getRelationshipVisual(d.type).markerId})`);

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

    // Follow settling positions only for a fresh search/root, until the user pans/zooms.
    const fitSearch = graphSearchActive && activeDisplayData.nodes.length > 0;
    if (fitSearch && lastCenteredSearchRef.current !== debouncedSearchQuery) {
      userInteractedWithGraphRef.current = false;
      lastCenteredSearchRef.current = debouncedSearchQuery;
    }
    const fitCurrent = () => {
      if (!fitSearch || userInteractedWithGraphRef.current || !zoomBehaviorRef.current) return;
      const view=fitGraphViewport(renderData.nodes,width,height);
      svg.call(zoomBehaviorRef.current.transform,d3.zoomIdentity.translate(view.x,view.y).scale(view.scale));
    };
    fitCurrent();
    simulationRef.current.on('tick.viewport', fitCurrent).on('end.viewport',fitCurrent);
    if (!graphSearchActive) lastCenteredSearchRef.current = '';

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
        simulationRef.current.on('tick', null).on('tick.viewport',null).on('end.viewport',null);
      }
      // Clear any remaining event listeners
      if (gRef.current) {
        gRef.current.selectAll('*').on('.drag', null);
      }
      d3.select(svgElement)
        .on('.zoom', null)
        .on('click.graph-background', null);
    };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDisplayData, activeGraphDataset, searchResultData, filteredData, graphSearchActive, graphViewMode, selectedOntology, activeSearchResultId, handleZoom, model.viewport?.width, model.viewport?.height]);
}
