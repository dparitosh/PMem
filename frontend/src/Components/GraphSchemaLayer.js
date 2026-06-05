import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import '../CSS/GraphHEB.css';
import { API_METHODS } from '../services/apiClient';
import { safeGet } from '../utils/safeAccess';

/**
 * GraphSchemaLayer Component
 * 
 * Displays the ONTOLOGY/SCHEMA LAYER:
 * - Hierarchical tree layout (top-down)
 * - Only OntologyClass nodes and relationships
 * - Property definitions (ObjectProperty, DatatypeProperty)
 * - Color: Blue (#4A90E2) for classes, Gray (#7F8C8D) for properties
 * - Suitable for understanding class hierarchy and schema structure
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

// D3 constants for schema layer
const SCHEMA_LINK_COLOR = '#4A90E2';
const SCHEMA_LINK_OPACITY = 0.7;
const SCHEMA_LINK_STROKE_WIDTH = 2;
const SCHEMA_NODE_RADIUS = 12;
const TREE_LEVEL_DISTANCE = 150;  // Distance between tree levels
const TREE_SIBLING_DISTANCE = 120; // Distance between sibling nodes
const SCHEMA_CLASS_COLOR = '#4A90E2';      // Blue for ontology classes
const SCHEMA_PROPERTY_COLOR = '#7F8C8D';   // Gray for properties
// SCHEMA_CONSTRAINT_COLOR intentionally removed (unused)

export const GraphSchemaLayer = ({ onNodeClick, selectedNode, highlightedNodes = [] }) => {
  const svgRef = useRef();
  const [data, setData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(1);

  // Fetch schema graph data
  useEffect(() => {
    const fetchSchemaGraph = async () => {
      try {
        setLoading(true);
        console.log('Fetching schema graph...');
        
        const response = await API_METHODS.graph.getSchemaGraph();
        
        if (!response || !response.data || !response.data.results) {
          throw new Error('Invalid schema graph response');
        }

        const results = response.data.results;
        const processedData = processSchemaData(results);
        
        setData(processedData);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch schema graph:', err);
        setError(`Failed to load schema graph: ${err.message}`);
        setData({ nodes: [], links: [] });
      } finally {
        setLoading(false);
      }
    };

    fetchSchemaGraph();
  }, []);

  // Process raw Neo4j data into D3-compatible format
  const processSchemaData = (results) => {
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
          const isProperty = row.n.labels && 
                           (row.n.labels.includes('ObjectProperty') || 
                            row.n.labels.includes('DatatypeProperty'));
          
          nodes.set(nodeId, {
            id: nodeId,
            label: row.n.labels && row.n.labels.join(':'),
            name: displayName,
            properties: row.n.properties || {},
            color: isProperty ? SCHEMA_PROPERTY_COLOR : SCHEMA_CLASS_COLOR,
            layerType: 'schema',
            isProperty: isProperty
          });
        }
      }

      if (row.m) {
        const nodeId = row.m.elementId;
        if (!nodes.has(nodeId)) {
          const displayName = resolveDisplayProp(row.m.properties) || 
                            (row.m.labels && row.m.labels[0]) || 
                            'Unknown';
          const isProperty = row.m.labels && 
                           (row.m.labels.includes('ObjectProperty') || 
                            row.m.labels.includes('DatatypeProperty'));
          
          nodes.set(nodeId, {
            id: nodeId,
            label: row.m.labels && row.m.labels.join(':'),
            name: displayName,
            properties: row.m.properties || {},
            color: isProperty ? SCHEMA_PROPERTY_COLOR : SCHEMA_CLASS_COLOR,
            layerType: 'schema',
            isProperty: isProperty
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

  // Render D3 visualization
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
      .attr('class', 'schema-graph-container');

    // Define arrow markers
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead-schema')
      .attr('markerWidth', 10)
      .attr('markerHeight', 10)
      .attr('refX', 20)
      .attr('refY', 3)
      .attr('orient', 'auto')
      .append('polygon')
      .attr('points', '0 0, 10 3, 0 6')
      .attr('fill', SCHEMA_LINK_COLOR);

    // Create tree layout
    const treeLayout = d3.tree()
      .size([width - 100, height - 100])
      .nodeSize([TREE_SIBLING_DISTANCE, TREE_LEVEL_DISTANCE]);

    // Build hierarchy from nodes and links
    const hierarchy = buildHierarchy(data.nodes, data.links);
    const root = d3.hierarchy(hierarchy);
    treeLayout(root);

    // Draw links
    g.selectAll('.schema-link')
      .data(root.links())
      .enter()
      .append('line')
      .attr('class', 'schema-link')
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y)
      .attr('stroke', SCHEMA_LINK_COLOR)
      .attr('stroke-opacity', SCHEMA_LINK_OPACITY)
      .attr('stroke-width', SCHEMA_LINK_STROKE_WIDTH)
      .attr('marker-end', 'url(#arrowhead-schema)');

    // Draw nodes
    const nodes = g.selectAll('.schema-node')
      .data(root.descendants())
      .enter()
      .append('circle')
      .attr('class', 'schema-node')
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)
      .attr('r', SCHEMA_NODE_RADIUS)
      .attr('fill', d => d.data.color || SCHEMA_CLASS_COLOR)
      .attr('stroke', d => highlightedNodes.includes(d.data.id) ? '#FFD700' : '#333')
      .attr('stroke-width', d => highlightedNodes.includes(d.data.id) ? 3 : 1)
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation();
        if (onNodeClick) onNodeClick(d.data);
      })
      .on('mouseover', function() {
        d3.select(this).attr('r', SCHEMA_NODE_RADIUS + 3);
      })
      .on('mouseout', function() {
        d3.select(this).attr('r', SCHEMA_NODE_RADIUS);
      });

    // Add labels
    g.selectAll('.schema-label')
      .data(root.descendants())
      .enter()
      .append('text')
      .attr('class', 'schema-label')
      .attr('x', d => d.x)
      .attr('y', d => d.y)
      .attr('text-anchor', 'middle')
      .attr('dy', '0.3em')
      .attr('font-size', '11px')
      .attr('font-weight', 600)
      .attr('fill', '#fff')
      .text(d => d.data.name.substring(0, 15))
      .style('pointer-events', 'none');

    // Add tooltip
    nodes.append('title')
      .text(d => `${d.data.label}\n${d.data.name}\n\nType: ${d.data.isProperty ? 'Property' : 'Class'}`);

    // Add zoom/pan
    const zoom = d3.zoom()
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
        setZoomLevel(event.transform.k);
      });
    
    svg.call(zoom);

  }, [data, highlightedNodes, onNodeClick]);

  // Build hierarchy from flat nodes and links for tree layout
  const buildHierarchy = (nodes, links) => {
    // Find root nodes (no incoming edges)
    const incoming = new Set();
    links.forEach(link => incoming.add(link.target));
    const roots = nodes.filter(n => !incoming.has(n.id));

    if (roots.length === 0) return nodes[0]; // Fallback

    const root = roots[0];
    const hierarchy = { ...root, children: [] };

    const buildChildren = (nodeId, parent, visited = new Set()) => {
      if (visited.has(nodeId)) return;
      visited.add(nodeId);

      const children = links
        .filter(link => link.source === nodeId)
        .map(link => {
          const childNode = nodes.find(n => n.id === link.target);
          if (childNode) {
            const child = { ...childNode, children: [] };
            buildChildren(childNode.id, child, visited);
            return child;
          }
          return null;
        })
        .filter(Boolean);

      parent.children = children;
    };

    buildChildren(root.id, hierarchy);
    return hierarchy;
  };

  if (loading) {
    return (
      <div className="schema-layer-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div>Loading schema graph...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="schema-layer-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#e74c3c' }}>
        <div>{error}</div>
      </div>
    );
  }

  return (
    <div className="schema-layer-container" style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: '12px', color: '#666', padding: '8px', borderBottom: '1px solid #ddd' }}>
        <strong>Schema Layer</strong> | Nodes: {data.nodes.length} | Links: {data.links.length} | Zoom: {zoomLevel.toFixed(2)}x
      </div>
      <svg 
        ref={svgRef}
        className="schema-graph"
        style={{ flex: 1, border: '1px solid #ddd', background: '#fafafa' }}
      />
    </div>
  );
};

export default GraphSchemaLayer;
