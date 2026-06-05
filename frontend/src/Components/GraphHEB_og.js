



import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import neo4j from 'neo4j-driver';
import '../CSS/GraphHEB.css';
import axios from 'axios';
 
// Initialize Neo4j Driver once outside the component.
const driver = neo4j.driver(
//   'bolt://localhost:7687',
  'bolt://localhost:7687',
  neo4j.auth.basic('neo4j', 'password'),
   { disableLosslessIntegers: true }
);
 
// Define constants for D3 parameters and styling
const NODE_ACTIVE_COLOR = '#802157';
const LINK_COLOR = '';
const LINK_OPACITY = 0.6;
const LINK_STROKE_WIDTH = 2;
const NODE_RADIUS = 14;
const FONT_SIZE = 14;
const LINK_DISTANCE = 100;
const CHARGE_STRENGTH = -300;
const COLLIDE_RADIUS = 60;
const ALPHA_TARGET_DRAG = 0.3;
const ALPHA_TARGET_END = 0;

// NEW CONSTANTS FOR CENTERING AND VIEWPORT
const CENTER_FORCE_STRENGTH = 0.05;
const VIEWPORT_PADDING = 50;

// NEW CONSTANTS FOR EXPAND/COLLAPSE
const EXPAND_SYMBOL_SIZE = 8;
const EXPAND_CIRCLE_RADIUS = 10;
const CONNECTION_LIMIT = 8;
 
// NEW CONSTANTS FOR ARROWHEADS
const ARROW_HEAD_LENGTH = 8;
const ARROW_HEAD_WIDTH = 4;
const ARROW_REF_X = NODE_RADIUS + 3; // Adjust so arrow starts slightly after node boundary
 
const GraphHEB = (props) => {
  const svgRef = useRef();
  const tooltipRef = useRef();
  const relationTooltipRef = useRef();
 
  const simulationRef = useRef(null);
  const gRef = useRef(null); // Ref for the main D3 group element
 
  const [data, setData] = useState({ nodes: [], links: [] });
  const [filteredData, setFilteredData] = useState({ nodes: [], links: [] });
  // const [activeNode, setActiveNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [result, setResult] = useState([]);
  
  // New state for expand/collapse functionality
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [loadingNodes, setLoadingNodes] = useState(new Set());
  const [fullDataset, setFullDataset] = useState({ nodes: [], links: [] });
  
  // New state to track initial data for reset functionality
  const [initialData, setInitialData] = useState({ nodes: [], links: [] });

  const color = {
    'MILESTONE': '#0a8276',
    'WORKPRODUCT': '#ffc400',
    'KlusaProject': '#00FFFF',
    'JiraProject': '#89CFF0',
    'SPS Legacy': '#ffce33',
    'Software': '#ff33f0',
    'Design Block': '#ff3339',
    'Chip': '#ec7063',
    'Document':'#DE3163'
  }

  const link_color = {
    'HAS_WORKPRODUCT': '#ffc400',
    'KLUSA_TO_IDPF': '#00FFFF',
    'HAS_MILESTONE': '#0a8276',
  }

 
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

  useEffect(() => {

    const nodesMap = new Map();
        const rawLinks = new Map();
        if(result?.length>0){
          result.forEach(record => {
            const n = record['n'];
            const r = record['r'];
              const m = record['m'];
              const nodeIdN = n.elementId;
              const nodeN = {
                  ...n.properties,
                  elementId: nodeIdN,
                  label: n.labels[0] || 'Node',
              }
            if (!nodesMap.has(nodeIdN)) {
              nodesMap.set(nodeIdN, nodeN );
            }
   
            if (r && m) {
              const nodeIdM = m.elementId;
              if (!nodesMap.has(nodeIdM)) {
                  nodesMap.set(nodeIdM, {
                  ...m.properties,
                  elementId:  nodeIdM,
                  label: m.labels[0] || 'Node',               
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
          const validatedLinks = [];
          finalLinks.forEach(link => {
            if (existingNodeIds.has(link.source) && existingNodeIds.has(link.target)) {
              validatedLinks.push(link);
            } else {
              console.warn(
                `Skipping potentially invalid link (ID: ${link.elementId}, Type: ${link.type}) ` +
                `due to missing node(s) after processing. Source: ${link.source} (${existingNodeIds.has(link.source) ? 'found' : 'MISSING'}) ` +
                `Target: ${link.target} (${existingNodeIds.has(link.target) ? 'found' : 'MISSING'})`
              );
            }
          });
   
          console.log('Fetched Nodes (validated):', nodes);
          console.log('Fetched Links (validated):', validatedLinks);
          props.setData({ nodes, links: validatedLinks });
   
          setData({ nodes, links: validatedLinks });
          setFilteredData({ nodes, links: validatedLinks });
          setFullDataset({ nodes, links: validatedLinks }); // Store full dataset
          setInitialData({ nodes, links: validatedLinks }); // Store initial default data
          setIsLoading(false);
        }else{
          if(result?.length==0  && searchQuery?.length>0){
            setIsLoading(false);
          }
        }
        
  }, [result]);
 
  // --- 1. Data Fetching from Neo4j (runs once on mount) ---
  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        axios.get("http://localhost:8000/graphvis").then(response => setResult(response.data.results));
        
      } catch (err) {
        console.error('Neo4j Data Fetch Error:', err);
        setError(`Failed to load graph data. Details: ${err.message}. Check console for more info.`);
      }
    };
 
    fetchData();
    
  }, []);
 
  // --- 2. Filter Data based on Search Query (runs on query/data change) ---
  useEffect(() => {
    if (!searchQuery) {
      setFilteredData(data);
      // setActiveNode(null);
      return;
    }
    setFilteredData({ nodes: [], links: [] })
    setIsLoading(true);
    const lowerCaseSearchQuery = searchQuery.toLowerCase();
      axios.post('http://localhost:8000/graphfilter', {
        search: lowerCaseSearchQuery
      }).then(response => { 
        setResult(response.data.results);
      });
      // console.log('setResult:', setResult)
    
    // const matchedNodes = data.nodes.filter(node =>
    //   (node.label && String(node.label).toLowerCase().includes(lowerCaseSearchQuery)) ||
    //   (node.name && String(node.name).toLowerCase().includes(lowerCaseSearchQuery)) ||
    //   (node.properties && Object.values(node.properties).some(val =>
    //     String(val).toLowerCase().includes(lowerCaseSearchQuery)
    //   )) ||
    //   Object.keys(node).some(key =>
    //     !['id', 'label', 'x', 'y', 'vx', 'vy', 'index', 'fx', 'fy', 'properties'].includes(key) &&
    //     String(node[key]).toLowerCase().includes(lowerCaseSearchQuery)
    //   )
    // );
 
    // const matchedNodeIds = new Set(matchedNodes.map(n => n.elementId));
    // const matchedLinks = data.links.filter(
    //   l => matchedNodeIds.has(l.source.elementId) && matchedNodeIds.has(l.target.elementId)
    // );
 
    // setFilteredData({ nodes: matchedNodes, links: matchedLinks });
    // props.setData({nodes: matchedNodes, links: matchedLinks});
    // setActiveNode(null);
  }, [searchQuery]);

  // Function to determine if a node has expandable connections
  const hasExpandableConnections = (nodeData) => {
    // Only show expand option for original search results and if not already expanded
    const isOriginalSearchResult = data.nodes.some(originalNode => originalNode.elementId === nodeData.elementId);
    const isNotExpanded = !expandedNodes.has(nodeData.elementId);
    const hasSearchQuery = !!searchQuery;
    
    console.log('hasExpandableConnections check:', {
      nodeId: nodeData.elementId,
      isOriginalSearchResult,
      isNotExpanded,
      hasSearchQuery,
      result: hasSearchQuery && isOriginalSearchResult && isNotExpanded
    });
    
    return hasSearchQuery && isOriginalSearchResult && isNotExpanded;
  };

  // Function to determine if a node can be collapsed
  const canCollapseNode = (nodeData) => {
    // Only show collapse option for original search result nodes that are expanded
    const isOriginalSearchResult = data.nodes.some(originalNode => originalNode.elementId === nodeData.elementId);
    const isExpanded = expandedNodes.has(nodeData.elementId);
    const hasSearchQuery = !!searchQuery;
    
    console.log('canCollapseNode check:', {
      nodeId: nodeData.elementId,
      isOriginalSearchResult,
      isExpanded,
      hasSearchQuery,
      result: hasSearchQuery && isOriginalSearchResult && isExpanded
    });
    
    return hasSearchQuery && isOriginalSearchResult && isExpanded;
  };

  // Function to expand a node using graphtraverse API - simplified single level expansion
  const expandNode = async (nodeId) => {
    console.log('expandNode called for:', nodeId);
    
    if (expandedNodes.has(nodeId)) {
      console.log('Node already expanded, skipping:', nodeId);
      return;
    }
    
    console.log('Starting expansion for node:', nodeId);
    setLoadingNodes(prev => new Set([...prev, nodeId]));
    
    try {
      console.log('Making API call to:', `http://localhost:8000/graphtraverse/${nodeId}`);
      const response = await axios.get(`http://localhost:8000/graphtraverse/${nodeId}`);
      
      console.log('API response received:', response.data);
      
      if (response.data && response.data.results) {
        // Start with existing nodes and links
        const newNodesMap = new Map();
        const newLinksMap = new Map();
        
        // Add existing nodes to prevent duplicates
        filteredData.nodes.forEach(node => {
          newNodesMap.set(node.elementId, node);
        });
        
        // Add existing links to prevent duplicates
        filteredData.links.forEach(link => {
          newLinksMap.set(link.elementId, link);
        });
        
        console.log('Processing', response.data.results.length, 'records from API');
        
        // Process the API response
        response.data.results.forEach(record => {
          const n = record['n'];
          const r = record['r'];
          const m = record['m'];
          
          // Add the source node (n) if not already present
          if (n) {
            const nodeIdN = n.elementId;
            const nodeN = {
              ...n.properties,
              elementId: nodeIdN,
              label: n.labels[0] || 'Node',
            };
            if (!newNodesMap.has(nodeIdN)) {
              newNodesMap.set(nodeIdN, nodeN);
              console.log('Added new node (n):', nodeIdN);
            }
          }
          
          // Add connected nodes (m) and relationships (r)
          if (r && m) {
            const nodeIdM = m.elementId;
            const nodeM = {
              ...m.properties,
              elementId: nodeIdM,
              label: m.labels[0] || 'Node',
            };
            if (!newNodesMap.has(nodeIdM)) {
              newNodesMap.set(nodeIdM, nodeM);
              console.log('Added new node (m):', nodeIdM);
            }
            
            const linkId = r.elementId;
            if (!newLinksMap.has(linkId)) {
              newLinksMap.set(linkId, {
                elementId: linkId,
                source: r.start,
                target: r.end,
                type: r.type,
                properties: r.properties,
              });
              console.log('Added new link:', linkId);
            }
          }
        });
        
        const finalNodes = Array.from(newNodesMap.values());
        const finalLinks = Array.from(newLinksMap.values());
        
        console.log('Final nodes count:', finalNodes.length, 'Final links count:', finalLinks.length);
        
        // Validate links
        const existingNodeIds = new Set(finalNodes.map(node => node.elementId));
        const validatedLinks = finalLinks.filter(link => 
          existingNodeIds.has(link.source) && existingNodeIds.has(link.target)
        );
        
        console.log('Validated links count:', validatedLinks.length);
        
        // Update datasets
        setFilteredData({ nodes: finalNodes, links: validatedLinks });
        setFullDataset({ nodes: finalNodes, links: validatedLinks });
        props.setData({ nodes: finalNodes, links: validatedLinks });
        
        console.log('Updated datasets');
      }
      
      setExpandedNodes(prev => new Set([...prev, nodeId]));
      console.log('Node marked as expanded:', nodeId);
      
    } catch (error) {
      console.error('Error expanding node:', nodeId, error);
    } finally {
      setLoadingNodes(prev => {
        const newSet = new Set(prev);
        newSet.delete(nodeId);
        return newSet;
      });
      console.log('Finished loading for node:', nodeId);
    }
  };

  // Function to collapse a node - returns to original search results
  const collapseNode = (nodeId) => {
    // Reset to the original search results, removing all expanded branches
    setFilteredData(data);
    setFullDataset(data);
    props.setData(data);
    
    // Remove this node from expanded set
    setExpandedNodes(prev => {
      const newSet = new Set(prev);
      newSet.delete(nodeId);
      return newSet;
    });
  };

  // Function to toggle node expansion with debouncing
  const toggleNodeExpansion = useCallback((nodeData) => {
    // Prevent multiple rapid clicks
    if (loadingNodes.has(nodeData.elementId)) {
      return;
    }
    
    if (expandedNodes.has(nodeData.elementId)) {
      collapseNode(nodeData.elementId);
    } else if (hasExpandableConnections(nodeData)) {
      expandNode(nodeData.elementId);
    }
  }, [expandedNodes, loadingNodes, hasExpandableConnections]);

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
    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    if (!gRef.current) {
      svg.selectAll('*').remove(); // Clear existing content on first render
      gRef.current = svg.append('g'); // Main group for graph elements
      // Initialize zoom behavior on the parent SVG
      svg.call(d3.zoom()
        .scaleExtent([0.1, 5])
        .on('zoom', ({ transform }) => {
          gRef.current.attr('transform', transform);
        })
      );
 
      // ENHANCEMENT: Define Arrowhead Marker in SVG defs
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
          .attr("fill", LINK_COLOR); // Fill color of the arrow (can be dynamic)
 
      console.log('D3 SVG and Arrowhead Marker initialized.');
    }


 
    if (filteredData.nodes.length === 0) {
      gRef.current.selectAll('*').remove();
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
      console.log('No nodes to display after filtering. Graph cleared.');
      return;
    }

    // Initialize positions for new nodes (especially for search results)
    initializeNodePositions(filteredData.nodes, width, height);

    // --- Initialize/Update Simulation ---
    if (!simulationRef.current) {
      simulationRef.current = d3.forceSimulation(filteredData.nodes)
        .force('link', d3.forceLink(filteredData.links).id(d => d.elementId).distance(LINK_DISTANCE))
        .force('charge', d3.forceManyBody().strength(CHARGE_STRENGTH))
        .force('center', d3.forceCenter(width / 2, height / 2).strength(CENTER_FORCE_STRENGTH))
        .force('collide', d3.forceCollide().radius(COLLIDE_RADIUS))
        .force('boundary', boundaryForce(width, height));
      console.log('D3 Simulation initialized.');
    } else {
      simulationRef.current.nodes(filteredData.nodes);
      simulationRef.current.force('link').links(filteredData.links); 
      simulationRef.current.force('center', d3.forceCenter(width / 2, height / 2).strength(CENTER_FORCE_STRENGTH));
      simulationRef.current.force('boundary', boundaryForce(width, height));
      simulationRef.current.alpha(1).restart();
      console.log('D3 Simulation updated and restarted.');
    }
 
    // --- D3 Data Binding and Drawing ---
    // Links (lines)
    const link = gRef.current.selectAll('.link')
      .data(filteredData.links, d => d.elementId)
      .join(
        enter => {
          const group = enter.append('line')
            .attr('class', 'link')
            .attr('stroke', LINK_COLOR)
            .attr('stroke-opacity', LINK_OPACITY)
            .attr('stroke-width', LINK_STROKE_WIDTH)
            // ENHANCEMENT: Apply the arrowhead marker
            .attr('marker-end', 'url(#arrowhead)')
            .on('mouseover', function (event, d) {
              d3.select(relationTooltipRef.current).style('z-index', 12);
              d3.select(relationTooltipRef.current).transition().duration(200).style('opacity', 0.9);
              d3.select(relationTooltipRef.current).html(
                `<strong>Type</strong>: ${d.type || 'N/A'}<br/>` +
                (d.properties ? Object.entries(d.properties).map(([k, v]) => `<strong>${k}</strong>: ${v}`).join('<br/>') : 'No properties')
              )
                .style('left', `${event.pageX + 10}px`)
                .style('top', `${event.pageY - 15}px`);
            })
          
            group.on('mouseout', () => {
              d3.select(relationTooltipRef.current).transition().duration(400).style('opacity', 0);
            });
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
 
    // Nodes (groups containing circle and text)
    const node = gRef.current.selectAll('.node-group')
      .data(filteredData.nodes, d => d.elementId)
      .join(
        enter => {
          const group = enter.append('g')
            .attr('class', 'node-group')
            .call(d3.drag()
              .on('start', dragstarted)
              .on('drag', dragged)
              .on('end', dragended)
            );

          // Main node circle
          group.append('circle')
            .attr('class', 'main-circle')
            .attr('r', NODE_RADIUS)
            .attr('fill', d => color[d.label] ?? '#00008B');

          // Node label text
          group.append('text')
            .attr('class', 'node-label')
            .text(d => { 
              if(d['label'] === 'MILESTONE'){
                return d['milestone_abbreviation']
              }else if(d['label'] === 'WORKPRODUCT'){
                return d['name']
              }else if(Object.keys(d).some(key=> key.startsWith('project_'))){
                return d['name']
              }else if(d['label'] === 'KlusaProject'){
                return d['name']
              }
              else if(d['label'] === 'JiraProject'){
                return d['jira_project_key']
              }
              else if(d['label'] === 'Chip'||d['label']==='Design Block'||d['label']==='Software'||d['label']==='SPS Legacy'||d['label']==='Document'){
                return d['name']
              }
               else{
                return d.label
              }})
            .attr('font-size', 10)
            .attr('dx', NODE_RADIUS + 5)
            .attr('dy', 3)
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
              console.log('Expand/Collapse clicked for node:', d.elementId, 'canExpand:', hasExpandableConnections(d), 'canCollapse:', canCollapseNode(d));
              if (hasExpandableConnections(d) || canCollapseNode(d)) {
                toggleNodeExpansion(d);
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
              if (canCollapseNode(d)) return '−'; // Minus for collapse
              if (hasExpandableConnections(d)) return '+'; // Plus for expand
              return ''; // No symbol
            });

          // Loading indicator
          group.append('circle')
            .attr('class', 'loading-indicator')
            .attr('r', NODE_RADIUS + 5)
            .attr('fill', 'none')
            .attr('stroke', '#2196F3')
            .attr('stroke-width', 2)
            .attr('stroke-dasharray', '5,5')
            .style('opacity', d => loadingNodes.has(d.elementId) ? 1 : 0)
            .style('pointer-events', 'none');

          // Main node interactions
          group.on('mouseover', function (event, d) {
            d3.select(this).select('.main-circle').attr('stroke', 'black').attr('stroke-width', 1.5);
            d3.select(tooltipRef.current).style('z-index', 12);
            d3.select(tooltipRef.current).transition().duration(200).style('opacity', 0.9);
            d3.select(tooltipRef.current).html(
              `<strong>Label</strong>: ${d.label || 'N/A'}<br/>` +
              Object.entries(d)
                .filter(([k]) => !['id', 'label', 'x', 'y', 'vx', 'vy', 'index', 'fx', 'fy', 'properties'].includes(k))
                .map(([k, v]) => `<strong>${k}</strong>: ${v}`).join('<br/>') +
              (d.properties ? `<br/>--- Properties ---<br/>` +
                Object.entries(d.properties).map(([k, v]) => `<strong>${k}</strong>: ${v}`).join('<br/>') : '')
            )
            .style('left', `${event.pageX + 10}px`)
            .style('top', `${event.pageY - 15}px`);
          })
          .on('mouseout', function () {
            d3.select(this).select('.main-circle').attr('stroke', null).attr('stroke-width', null);
            d3.select(tooltipRef.current).transition().duration(400).style('opacity', 0);
          });

          return group;
        },
        update => {
          update.select('.main-circle')
            .attr('fill', d => color[d.label] ?? '#00008B');
          
          update.select('.node-label')
            .text(d => d.label || d.elementId);

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
              if (canCollapseNode(d)) return '−'; // Minus for collapse
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
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);
      node.attr('transform', d => `translate(${d.x},${d.y})`);
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
      
      svg.transition()
        .duration(750)
        .call(
          d3.zoom().transform,
          transform
        );
    }
 
    return () => {
      if (simulationRef.current) {
        simulationRef.current.stop();
        console.log('D3 Simulation stopped on component unmount.');
      }
    };
 
  }, [filteredData, searchQuery, dragstarted, dragged, dragended]);

  // Keyboard shortcuts for expand/collapse
  useEffect(() => {
    const handleKeyPress = (event) => {
      if (event.key === 'Escape') {
        // Collapse all nodes and reset to original search results
        setExpandedNodes(new Set());
        setFilteredData(data);
        setFullDataset(data);
        props.setData(data);
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [data]);

  // Reset expanded nodes when search query changes
  useEffect(() => {
    setExpandedNodes(new Set());
  }, [searchQuery]);
 
  return (
    <div style={{position: 'relative', marginLeft: '30px',width: '98%', height: '80vh', display: 'flex', flexDirection: 'column' }}>
       <div style={{
         position: 'absolute',
         zIndex: 10,
         left: 10,
         top: 50,
         display: 'flex',
         gap: '10px',
         alignItems: 'center'
       }}>
         <input
           type="text"
           placeholder="Search nodes..."
           style={{
             padding: '8px',
             borderRadius: '4px',
             border: '1px solid #ccc',
             minWidth: '200px'
           }}
           onKeyDown={e => { if (e.key === 'Enter') {setSearchQuery(e.target.value)} }}
         />
         {searchQuery && (
           <button
             onClick={() => {
               setSearchQuery('');
               setExpandedNodes(new Set());
               // Reset to initial default data
               setData(initialData);
               setFilteredData(initialData);
               setFullDataset(initialData);
               props.setData(initialData);
               // Clear the search input
               const searchInput = document.querySelector('input[type="text"]');
               if (searchInput) searchInput.value = '';
             }}
             style={{
               padding: '8px 12px',
               borderRadius: '4px',
               border: '1px solid #dc3545',
               backgroundColor: '#fff',
               cursor: 'pointer',
               fontSize: '12px',
               color: '#dc3545',
               fontWeight: 'bold',
               transition: 'all 0.2s ease'
             }}
             onMouseEnter={(e) => {
               e.target.style.backgroundColor = '#dc3545';
               e.target.style.color = '#fff';
             }}
             onMouseLeave={(e) => {
               e.target.style.backgroundColor = '#fff';
               e.target.style.color = '#dc3545';
             }}
             title="Reset to default view"
           >
             ✕ Reset
           </button>
         )}
       </div> 
      {isLoading && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 11, background: 'rgba(255,255,255,0.8)', padding: '20px', borderRadius: '8px', textAlign: 'center', boxShadow: '0 2px 10px rgba(0,0,0,0.1)' }}>
          Loading graph data...
        </div>
      )}
      {error && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 11, background: 'rgba(255,0,0,0.7)', color: 'white', padding: '20px', borderRadius: '8px', textAlign: 'center', boxShadow: '0 2px 10px rgba(0,0,0,0.1)' }}>
          Error: {error}
        </div>
      )}
      {!isLoading && !error && filteredData.nodes.length === 0 && searchQuery && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 11, background: 'rgba(255,255,255,0.8)', padding: '20px', borderRadius: '8px', textAlign: 'center', boxShadow: '0 2px 10px rgba(0,0,0,0.1)' }}>
          No nodes found for "{searchQuery}"
        </div>
      )}
      {!isLoading && !error && data.nodes.length === 0 && !searchQuery && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 11, background: 'rgba(255,255,255,0.8)', padding: '20px', borderRadius: '8px', textAlign: 'center', boxShadow: '0 2px 10px rgba(0,0,0,0.1)' }}>
          No graph data available from Neo4j.
        </div>
      )}
 
      <svg ref={svgRef} style={{ width: '100%', height: '100%', flexGrow: 1, marginTop: '45px' }}></svg>
 
      <div ref={tooltipRef} className="tooltip" style={{
        position: 'absolute', opacity: 0, background: 'rgba(0,0,0,0.7)', color: 'white',
        padding: '8px', borderRadius: '4px', pointerEvents: 'none', maxWidth: '300px', fontSize: '0.8em', zIndex: 12
      }} />
      <div ref={relationTooltipRef} className="tooltip" style={{
        position: 'absolute', opacity: 0, background: 'rgba(0,0,0,0.7)', color: 'white',
        padding: '8px', borderRadius: '4px', pointerEvents: 'none', maxWidth: '300px', fontSize: '0.8em', zIndex: 12
      }} />
    </div>
  );
};
 
export default GraphHEB;








