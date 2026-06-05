import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import '../CSS/GraphHEB.css';
import { apiClient } from '../services/apiClient';
import { safeGet } from '../utils/safeAccess';

/**
 * GraphInstanceLayer Component
 * 
 * Displays the INSTANCE/CONTEXTUAL LAYER:
 * - Organic/network force-directed layout
 * - Real entities and relationships (instances only)
 * - Includes events, transactions, processes
 * - Includes time, provenance, and contextual metadata
 * - Color coding:
 *   • Green (#27AE60) for regular instances
 *   • Yellow (#F39C12) for contextual qualifiers (time, source, rules)
 * - Suitable for understanding real-world connections and business processes
 */

const DISPLAY_NAME_PROPERTY = ['name', 'title', 'code', 'key', 'abbreviation'];

const resolveDisplayProp = (props) => {
  if (!props || !DISPLAY_NAME_PROPERTY || DISPLAY_NAME_PROPERTY.length === 0) return null;
  for (const key of DISPLAY_NAME_PROPERTY) {
    const value = safeGet(props, key, null);
    if (value != null) return String(value);
  }
  return null;
};

// D3 constants for instance layer
const INSTANCE_LINK_COLOR = '#4A90E2';
const INSTANCE_LINK_OPACITY = 0.7;
const INSTANCE_LINK_STROKE_WIDTH = 2;
const INSTANCE_NODE_RADIUS = 14;
const LINK_DISTANCE = 100;
const CHARGE_STRENGTH = -150;
const COLLIDE_RADIUS = 40;

// Color scheme for instances
const INSTANCE_ENTITY_COLOR = '#27AE60';      // Green for regular instances
const INSTANCE_CONTEXTUAL_COLOR = '#F39C12';  // Yellow for contextual/time-related
const INSTANCE_PROCESS_COLOR = '#3498DB';     // Blue for processes
const INSTANCE_EVENT_COLOR = '#E74C3C';       // Red for events

// escapeHtml intentionally omitted here; use centralized sanitizer where needed

// Determine node color based on labels and properties
const getInstanceNodeColor = (node) => {
  if (!node) return INSTANCE_ENTITY_COLOR;
  
  const labels = node.label ? node.label.split(':') : [];
  const props = node.properties || {};

  // Check for contextual/time-related
  if (node.color === '#F39C12' || props.timestamp || props.created_at || props.provenance) {
    return INSTANCE_CONTEXTUAL_COLOR;
  }

  // Check for process/event types
  if (labels.includes('Process') || props.process_type) {
    return INSTANCE_PROCESS_COLOR;
  }
  if (labels.includes('Event') || labels.includes('Transaction')) {
    return INSTANCE_EVENT_COLOR;
  }

  return INSTANCE_ENTITY_COLOR;
};

export const GraphInstanceLayer = ({ onNodeClick, selectedNode, highlightedNodes = [] }) => {
  const svgRef = useRef();
  const simulationRef = useRef();
  const [data, setData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [stats, setStats] = useState({ entityCount: 0, processCount: 0, eventCount: 0 });

  // Fetch instance graph data
  useEffect(() => {
    const fetchInstanceGraph = async () => {
      try {
        setLoading(true);
        console.log('Fetching instance graph...');
        
        const response = await apiClient.get('/instance-graph');
        
        if (!response || !response.data || !response.data.results) {
          throw new Error('Invalid instance graph response');
        }

        const results = response.data.results;
        const processedData = processInstanceData(results);
        
        setData(processedData);
        
        // Calculate statistics
        const entityCount = processedData.nodes.filter(n => !n.isProcess && !n.isEvent).length;
        const processCount = processedData.nodes.filter(n => n.isProcess).length;
        const eventCount = processedData.nodes.filter(n => n.isEvent).length;
        setStats({ entityCount, processCount, eventCount });
        
        setError(null);
      } catch (err) {
        console.error('Failed to fetch instance graph:', err);
        setError(`Failed to load instance graph: ${err.message}`);
        setData({ nodes: [], links: [] });
      } finally {
        setLoading(false);
      }
    };

    fetchInstanceGraph();
  }, []);

  // Process raw Neo4j data into D3-compatible format
  const processInstanceData = (results) => {
    const nodes = new Map();
    const links = [];
    const processedLinks = new Set();

    // Extract unique nodes
    results.forEach(row => {
      if (row.n) {
        const nodeId = row.n.elementId;
        if (!nodes.has(nodeId)) {
          const displayName = resolveDisplayProp(row.n.properties) || 
                            (row.n.labels && row.n.labels[0]) || 
                            'Unknown';
          const labels = row.n.labels || [];
          const isProcess = labels.includes('Process') || row.n.properties?.process_type;
          const isEvent = labels.includes('Event') || labels.includes('Transaction');
          const isContextual = row.n.color === '#F39C12';
          
          nodes.set(nodeId, {
            id: nodeId,
            label: labels.join(':'),
            name: displayName,
            properties: row.n.properties || {},
            color: getInstanceNodeColor(row.n),
            layerType: 'instance',
            isProcess,
            isEvent,
            isContextual
          });
        }
      }

      if (row.m) {
        const nodeId = row.m.elementId;
        if (!nodes.has(nodeId)) {
          const displayName = resolveDisplayProp(row.m.properties) || 
                            (row.m.labels && row.m.labels[0]) || 
                            'Unknown';
          const labels = row.m.labels || [];
          const isProcess = labels.includes('Process') || row.m.properties?.process_type;
          const isEvent = labels.includes('Event') || labels.includes('Transaction');
          const isContextual = row.m.color === '#F39C12';
          
          nodes.set(nodeId, {
            id: nodeId,
            label: labels.join(':'),
            name: displayName,
            properties: row.m.properties || {},
            color: getInstanceNodeColor(row.m),
            layerType: 'instance',
            isProcess,
            isEvent,
            isContextual
          });
        }
      }
    });

    // Extract relationships
    results.forEach(row => {
      if (row.r && row.n && row.m) {
        const linkKey = `${row.r.start}-${row.r.type}-${row.r.end}`;
        if (!processedLinks.has(linkKey)) {
          links.push({
            source: row.r.start,
            target: row.r.end,
            type: row.r.type,
            properties: row.r.properties || {}
          });
          processedLinks.add(linkKey);
        }
      }
    });

    return {
      nodes: Array.from(nodes.values()),
      links: links
    };
  };

  // Render D3 visualization with force simulation
  useEffect(() => {
    if (!svgRef.current || !data.nodes.length) return;

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    // Create SVG
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove(); // Clear previous

    const g = svg
      .attr('width', width)
      .attr('height', height)
      .append('g')
      .attr('class', 'instance-graph-container');

    // Define arrow markers
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead-instance')
      .attr('markerWidth', 10)
      .attr('markerHeight', 10)
      .attr('refX', 20)
      .attr('refY', 3)
      .attr('orient', 'auto')
      .append('polygon')
      .attr('points', '0 0, 10 3, 0 6')
      .attr('fill', INSTANCE_LINK_COLOR);

    // Create force simulation
    const simulation = d3.forceSimulation(data.nodes)
      .force('link', d3.forceLink(data.links)
        .id(d => d.id)
        .distance(LINK_DISTANCE))
      .force('charge', d3.forceManyBody().strength(CHARGE_STRENGTH))
      .force('collide', d3.forceCollide().radius(COLLIDE_RADIUS))
      .force('center', d3.forceCenter(width / 2, height / 2).strength(0.05))
      .on('tick', () => {
        links.attr('x1', d => d.source.x)
          .attr('y1', d => d.source.y)
          .attr('x2', d => d.target.x)
          .attr('y2', d => d.target.y);

        nodes.attr('cx', d => d.x)
          .attr('cy', d => d.y);

        labels.attr('x', d => d.x)
          .attr('y', d => d.y);
      });

    simulationRef.current = simulation;

    // Draw links
    const links = g.selectAll('.instance-link')
      .data(data.links)
      .enter()
      .append('line')
      .attr('class', 'instance-link')
      .attr('stroke', INSTANCE_LINK_COLOR)
      .attr('stroke-opacity', INSTANCE_LINK_OPACITY)
      .attr('stroke-width', INSTANCE_LINK_STROKE_WIDTH)
      .attr('marker-end', 'url(#arrowhead-instance)');

    // Draw nodes
    const nodes = g.selectAll('.instance-node')
      .data(data.nodes)
      .enter()
      .append('circle')
      .attr('class', 'instance-node')
      .attr('r', INSTANCE_NODE_RADIUS)
      .attr('fill', d => d.color)
      .attr('stroke', d => highlightedNodes.includes(d.id) ? '#FFD700' : '#333')
      .attr('stroke-width', d => highlightedNodes.includes(d.id) ? 3 : 1)
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation();
        if (onNodeClick) onNodeClick(d);
      })
      .on('mouseover', function(event, d) {
        d3.select(this).attr('r', INSTANCE_NODE_RADIUS + 3);
      })
      .on('mouseout', function(event, d) {
        d3.select(this).attr('r', INSTANCE_NODE_RADIUS);
      });

    // Make nodes draggable
    nodes.call(d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      }));

    // Add labels
    const labels = g.selectAll('.instance-label')
      .data(data.nodes)
      .enter()
      .append('text')
      .attr('class', 'instance-label')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.3em')
      .attr('font-size', '11px')
      .attr('font-weight', 600)
      .attr('fill', '#fff')
      .text(d => d.name.substring(0, 15))
      .style('pointer-events', 'none');

    // Add tooltips
    nodes.append('title')
      .text(d => {
        let tooltip = `${d.label}\n${d.name}`;
        if (d.properties.timestamp) tooltip += `\nTime: ${d.properties.timestamp}`;
        if (d.properties.source_tag) tooltip += `\nSource: ${d.properties.source_tag}`;
        return tooltip;
      });

    // Add zoom/pan
    const zoom = d3.zoom()
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
        setZoomLevel(event.transform.k);
      });
    
    svg.call(zoom);

  }, [data, highlightedNodes, onNodeClick]);

  if (loading) {
    return (
      <div className="instance-layer-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div>Loading instance graph...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="instance-layer-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#e74c3c' }}>
        <div>{error}</div>
      </div>
    );
  }

  return (
    <div className="instance-layer-container" style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: '12px', color: '#666', padding: '8px', borderBottom: '1px solid #ddd' }}>
        <strong>Instance Layer</strong> | 
        Entities: {stats.entityCount} | 
        Processes: {stats.processCount} | 
        Events: {stats.eventCount} | 
        Links: {data.links.length} | 
        Zoom: {zoomLevel.toFixed(2)}x
      </div>
      <div style={{ flex: 1, display: 'flex' }}>
        <svg 
          ref={svgRef}
          className="instance-graph"
          style={{ flex: 1, border: '1px solid #ddd', background: '#fafafa' }}
        />
        <div style={{ width: '200px', borderLeft: '1px solid #ddd', padding: '8px', overflow: 'auto', fontSize: '11px', background: '#fff' }}>
          <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>Legend:</div>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '6px' }}>
            <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#27AE60', marginRight: '6px' }}></div>
            <span>Entities</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '6px' }}>
            <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#3498DB', marginRight: '6px' }}></div>
            <span>Processes</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '6px' }}>
            <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#E74C3C', marginRight: '6px' }}></div>
            <span>Events</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '6px' }}>
            <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#F39C12', marginRight: '6px' }}></div>
            <span>Contextual</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GraphInstanceLayer;
