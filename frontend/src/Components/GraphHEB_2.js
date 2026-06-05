import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import neo4j from 'neo4j-driver';
import '../CSS/GraphHEB.css';
import axios from 'axios';
 
// Initialize Neo4j Driver once outside the component.
// const driver = neo4j.driver(
// //   'bolt://localhost:7687',
//   'XXXX',
//   neo4j.auth.basic('neo4j', 'XXXX'),
//    { disableLosslessIntegers: true }
// );
 
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

// NEW CONSTANTS FOR BIDIRECTIONAL LINK SEPARATION
const LINK_OFFSET_DISTANCE = 20; // Pixels to offset parallel links
 
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
  
  // Track which nodes were added by each expansion
  const [nodeExpansions, setNodeExpansions] = useState(new Map());

  // Generic color function for any node type
  const getNodeColor = (label) => {
    if (!label) return '#808080'; // Gray fallback for undefined labels
    
    // Generate consistent color based on label hash
    const hash = label.split('').reduce((a, b) => {
      a = ((a << 5) - a) + b.charCodeAt(0);
      return a & a;
    }, 0);
    
    // Convert hash to HSL color for better color distribution
    const hue = Math.abs(hash) % 360;
    const saturation = 70; // Fixed saturation for consistency
    const lightness = 50; // Increased lightness for better visibility
    
    const color = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
    return color;
  };

  // Generic color function for link types
  const getLinkColor = (linkType) => {
    // Generate consistent color based on link type hash
    const hash = linkType.split('').reduce((a, b) => {
      a = ((a << 5) - a) + b.charCodeAt(0);
      return a & a;
    }, 0);
    
    // Convert hash to HSL color for better color distribution
    const hue = Math.abs(hash) % 360;
    const saturation = 60; // Slightly lower saturation for links
    const lightness = 40; // Darker for better visibility against background
    
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  };

  // Function to process links and add offset information for bidirectional relationships
  const processLinksForOffset = (links) => {
    // Group links by node pairs (regardless of direction)
    const linkPairs = new Map();
    
    links.forEach(link => {
      // Create a consistent key for node pairs (sorted to handle both directions)
      const sourceId = typeof link.source === 'object' ? 
        (link.source.elementId || link.source.id || JSON.stringify(link.source)) : 
        link.source;
      const targetId = typeof link.target === 'object' ? 
        (link.target.elementId || link.target.id || JSON.stringify(link.target)) : 
        link.target;
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
    
    return links;
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

  // Helper function to safely extract node ID
  const getNodeId = (node) => {
    // Try different possible ID field names
    return node.elementId || node.id || node._id || node.identity || 
           (node.properties && (node.properties.id || node.properties.elementId)) ||
           JSON.stringify(node); // Fallback to stringified node as ID
  };

  // Helper function to safely extract node label/type
  const getNodeLabel = (node) => {
    // Try different possible label sources
    if (node.labels && node.labels.length > 0) return node.labels[0];
    if (node.label) return node.label;
    if (node.type) return node.type;
    if (node.properties) {
      // Check for common property names used as labels
      const labelProps = ['type', 'label', 'category', 'kind', 'class'];
      for (const prop of labelProps) {
        if (node.properties[prop]) return node.properties[prop];
      }
    }
    return 'Unknown'; // Final fallback
  };

  // Helper function to safely extract display name
  const getDisplayName = (node) => {
    console.log('getDisplayName called with:', node);
    
    // Try different possible name sources in order of preference
    const nameProps = ['name', 'title', 'label', 'displayName', 'text', 'value'];
    
    // First check direct properties
    for (const prop of nameProps) {
      if (node[prop]) {
        console.log(`Found display name in direct property '${prop}':`, node[prop]);
        return String(node[prop]);
      }
    }
    
    // Then check nested properties
    if (node.properties) {
      for (const prop of nameProps) {
        if (node.properties[prop]) {
          console.log(`Found display name in nested property '${prop}':`, node.properties[prop]);
          return String(node.properties[prop]);
        }
      }
    }
    
    // Fallback to node type/label
    const fallback = getNodeLabel(node);
    console.log('Using fallback label:', fallback);
    return fallback;
  };

  // Helper function to safely extract relationship type
  const getRelationshipType = (relationship) => {
    return relationship.type || relationship.label || 
           (relationship.properties && relationship.properties.type) ||
           'UNKNOWN_RELATION';
  };

  useEffect(() => {
    console.log('=== DATA PROCESSING START ===');
    console.log('Raw result data:', result);

    try {
      const nodesMap = new Map();
      const rawLinks = new Map();
      
      if(result?.length > 0){
        result.forEach((record, index) => {
          console.log(`Processing record ${index}:`, record);
          
          // Handle different possible record structures
          let n, r, m;
          
          if (record && typeof record === 'object') {
            // Standard structure: record['n'], record['r'], record['m']
            n = record['n'] || record.n;
            r = record['r'] || record.r;
            m = record['m'] || record.m;
            
            // Alternative structures - handle cases where properties might be named differently
            if (!n && !r && !m) {
              // Try to extract from other possible structures
              const keys = Object.keys(record);
              console.log('Trying alternative extraction from keys:', keys);
              
              // Look for node-like objects
              const possibleNodes = keys.filter(key => {
                const obj = record[key];
                return obj && typeof obj === 'object' && 
                       (obj.labels || obj.label || obj.properties || obj.elementId || obj.id);
              });
              
              // Look for relationship-like objects
              const possibleRels = keys.filter(key => {
                const obj = record[key];
                return obj && typeof obj === 'object' && 
                       (obj.type || obj.start || obj.end || obj.source || obj.target);
              });
              
              if (possibleNodes.length >= 1) n = record[possibleNodes[0]];
              if (possibleNodes.length >= 2) m = record[possibleNodes[1]];
              if (possibleRels.length >= 1) r = record[possibleRels[0]];
              
              console.log('Alternative extraction result:', { n, r, m });
            }
          }
          
          console.log('Record components:', { n, r, m });

          // Process first node (n)
          if (n) {
            try {
              const nodeIdN = getNodeId(n);
              const nodeLabel = getNodeLabel(n);
              const displayName = getDisplayName(n);
              
              console.log('Processing node N:', {
                nodeId: nodeIdN,
                label: nodeLabel,
                displayName: displayName,
                originalNode: n
              });

              const nodeN = {
                ...(n.properties || {}), // Safely spread properties
                elementId: nodeIdN,
                label: nodeLabel,
                name: displayName, // Ensure name is always available
                _originalNode: n // Keep reference for debugging
              };

              if (!nodesMap.has(nodeIdN)) {
                nodesMap.set(nodeIdN, nodeN);
                console.log('Added node N to map:', nodeN);
              }
            } catch (nodeError) {
              console.error('Error processing node N:', nodeError, n);
            }
          }

          // Process relationship and second node (r, m)
          if (r && m) {
            try {
              const nodeIdM = getNodeId(m);
              const nodeLabelM = getNodeLabel(m);
              const displayNameM = getDisplayName(m);
              
              console.log('Processing node M:', {
                nodeId: nodeIdM,
                label: nodeLabelM,
                displayName: displayNameM,
                originalNode: m
              });

              if (!nodesMap.has(nodeIdM)) {
                const nodeM = {
                  ...(m.properties || {}), // Safely spread properties
                  elementId: nodeIdM,
                  label: nodeLabelM,
                  name: displayNameM, // Ensure name is always available
                  _originalNode: m // Keep reference for debugging
                };
                nodesMap.set(nodeIdM, nodeM);
                console.log('Added node M to map:', nodeM);
              }

              // Process relationship
              const linkId = getNodeId(r);
              const relationshipType = getRelationshipType(r);
              
              console.log('Processing relationship:', {
                linkId: linkId,
                type: relationshipType,
                source: r.start || r.source || getNodeId(n),
                target: r.end || r.target || getNodeId(m),
                originalRel: r
              });

              if (!rawLinks.has(linkId)) {
                rawLinks.set(linkId, {
                  elementId: linkId,
                  source: r.start || r.source || getNodeId(n),
                  target: r.end || r.target || getNodeId(m),
                  type: relationshipType,
                  properties: r.properties || {},
                  _originalRelationship: r // Keep reference for debugging
                });
                console.log('Added relationship to map');
              }
            } catch (relError) {
              console.error('Error processing relationship/node M:', relError, { r, m });
            }
          }
        });

        const nodes = Array.from(nodesMap.values());
        const finalLinks = Array.from(rawLinks.values());
        
        console.log('=== PROCESSING COMPLETE ===');
        console.log('Total nodes processed:', nodes.length);
        console.log('Total links processed:', finalLinks.length);
        console.log('Sample nodes:', nodes.slice(0, 3));
        console.log('Sample links:', finalLinks.slice(0, 3));

        // Validate links
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
            console.warn('Available node IDs:', Array.from(existingNodeIds));
            console.warn('Link details:', link);
          }
        });

        console.log('Final validated data:', {
          nodes: nodes.length,
          links: validatedLinks.length
        });

        // Only update state if we have valid data
        if (nodes.length > 0) {
          // Update all state
          props.setData({ nodes, links: validatedLinks });
          setData({ nodes, links: validatedLinks });
          setFilteredData({ nodes, links: validatedLinks });
          setFullDataset({ nodes, links: validatedLinks });
          setInitialData({ nodes, links: validatedLinks });
          setError(null); // Clear any previous errors
        } else {
          setError('No valid nodes found in the data. The database schema might not be compatible with this visualization.');
          console.error('No valid nodes found after processing');
        }
        
        setIsLoading(false);
      } else {
        console.log('No result data to process');
        if(result?.length === 0 && searchQuery?.length > 0){
          setIsLoading(false);
        }
      }
    } catch (processingError) {
      console.error('Critical error in data processing:', processingError);
      setError(`Data processing failed: ${processingError.message}. The database schema may not be supported.`);
      setIsLoading(false);
    }
    
    console.log('=== DATA PROCESSING END ===');
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
      expandedNodes: Array.from(expandedNodes),
      dataNodes: data.nodes.map(n => n.elementId),
      result: hasSearchQuery && isOriginalSearchResult && isNotExpanded
    });
    
    return hasSearchQuery && isOriginalSearchResult && isNotExpanded;
  };

  // Function to determine if a node can be collapsed
  const canCollapseNode = (nodeData) => {
    // Only show collapse option for nodes that are currently expanded
    // This means only the original node that was expanded should show the collapse button
    const isExpanded = expandedNodes.has(nodeData.elementId);
    const hasSearchQuery = !!searchQuery;
    
    console.log('canCollapseNode check:', {
      nodeId: nodeData.elementId,
      isExpanded,
      hasSearchQuery,
      expandedNodes: Array.from(expandedNodes),
      result: hasSearchQuery && isExpanded
    });
    
    return hasSearchQuery && isExpanded;
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
    
    // Track nodes that will be added by this expansion
    const addedNodeIds = new Set();
    const addedLinkIds = new Set();
    
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
        
        // Process the API response using the same robust helper functions
        response.data.results.forEach((record, index) => {
          console.log(`Processing expansion record ${index}:`, record);
          
          const n = record['n'];
          const r = record['r'];
          const m = record['m'];
          
          // Add the source node (n) if not already present
          if (n) {
            const nodeIdN = getNodeId(n);
            const nodeLabel = getNodeLabel(n);
            const displayName = getDisplayName(n);
            
            const nodeN = {
              ...(n.properties || {}),
              elementId: nodeIdN,
              label: nodeLabel,
              name: displayName,
              _originalNode: n
            };
            
            if (!newNodesMap.has(nodeIdN)) {
              newNodesMap.set(nodeIdN, nodeN);
              addedNodeIds.add(nodeIdN);
              console.log('Added new node (n):', nodeIdN, nodeN);
            }
          }
          
          // Add connected nodes (m) and relationships (r)
          if (r && m) {
            const nodeIdM = getNodeId(m);
            const nodeLabelM = getNodeLabel(m);
            const displayNameM = getDisplayName(m);
            
            const nodeM = {
              ...(m.properties || {}),
              elementId: nodeIdM,
              label: nodeLabelM,
              name: displayNameM,
              _originalNode: m
            };
            
            if (!newNodesMap.has(nodeIdM)) {
              newNodesMap.set(nodeIdM, nodeM);
              addedNodeIds.add(nodeIdM);
              console.log('Added new node (m):', nodeIdM, nodeM);
            }
            
            const linkId = getNodeId(r);
            const relationshipType = getRelationshipType(r);
            
            if (!newLinksMap.has(linkId)) {
              newLinksMap.set(linkId, {
                elementId: linkId,
                source: r.start || r.source || getNodeId(n),
                target: r.end || r.target || getNodeId(m),
                type: relationshipType,
                properties: r.properties || {},
                _originalRelationship: r
              });
              addedLinkIds.add(linkId);
              console.log('Added new link:', linkId, relationshipType);
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
      
      // Store which nodes and links were added by this expansion
      console.log('=== STORING EXPANSION TRACKING ===');
      console.log('Node being expanded:', nodeId);
      console.log('Added node IDs:', Array.from(addedNodeIds));
      console.log('Added link IDs:', Array.from(addedLinkIds));
      
      setNodeExpansions(prev => {
        const newMap = new Map([...prev, [nodeId, { addedNodeIds, addedLinkIds }]]);
        console.log('Updated nodeExpansions map:', Array.from(newMap.entries()));
        return newMap;
      });
      
      setExpandedNodes(prev => {
        const newSet = new Set([...prev, nodeId]);
        console.log('Updated expandedNodes set:', Array.from(newSet));
        return newSet;
      });
      
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

  // Function to collapse a node - removes only the nodes/links added by that expansion
  const collapseNode = (nodeId) => {
    console.log('=== COLLAPSE FUNCTION START ===');
    console.log('Collapsing node:', nodeId);
    console.log('Current nodeExpansions:', Array.from(nodeExpansions.entries()));
    console.log('Current expandedNodes:', Array.from(expandedNodes));
    console.log('Current filteredData nodes:', filteredData.nodes.map(n => n.elementId));
    
    // Get the expansion info for this node
    const expansionInfo = nodeExpansions.get(nodeId);
    if (!expansionInfo) {
      console.log('ERROR: No expansion info found for node:', nodeId);
      console.log('Available expansions:', Array.from(nodeExpansions.keys()));
      return;
    }
    
    const { addedNodeIds, addedLinkIds } = expansionInfo;
    console.log('Nodes to remove:', Array.from(addedNodeIds));
    console.log('Links to remove:', Array.from(addedLinkIds));
    
    // Debug: Check if the nodes to be removed are actually in the current data
    const currentNodeIds = new Set(filteredData.nodes.map(n => n.elementId));
    const nodesToRemove = Array.from(addedNodeIds).filter(id => currentNodeIds.has(id));
    console.log('Nodes that will actually be removed (present in current data):', nodesToRemove);
    
    // Remove the nodes and links that were added by this expansion
    const filteredNodes = filteredData.nodes.filter(node => {
      const shouldKeep = !addedNodeIds.has(node.elementId);
      if (!shouldKeep) {
        console.log('Removing node:', node.elementId, node.name || node.label);
      }
      return shouldKeep;
    });
    
    const filteredLinks = filteredData.links.filter(link => {
      const shouldKeep = !addedLinkIds.has(link.elementId);
      if (!shouldKeep) {
        console.log('Removing link:', link.elementId, link.type);
      }
      return shouldKeep;
    });
    
    console.log('Nodes before collapse:', filteredData.nodes.length, 'after:', filteredNodes.length);
    console.log('Links before collapse:', filteredData.links.length, 'after:', filteredLinks.length);
    console.log('Remaining node IDs:', filteredNodes.map(n => n.elementId));
    
    // Validate that we're actually removing nodes
    if (filteredNodes.length === filteredData.nodes.length) {
      console.error('ERROR: No nodes were actually removed! This indicates a problem with the collapse logic.');
      console.error('Check if addedNodeIds match the actual node elementIds');
      console.error('addedNodeIds:', Array.from(addedNodeIds));
      console.error('current node elementIds:', filteredData.nodes.map(n => n.elementId));
    }
    
    // Update datasets
    const newData = { nodes: filteredNodes, links: filteredLinks };
    console.log('Setting new data:', {
      nodeCount: newData.nodes.length,
      linkCount: newData.links.length
    });
    
    setFilteredData(newData);
    setFullDataset(newData);
    props.setData(newData);
    
    // Remove this node from expanded set and expansion tracking
    setExpandedNodes(prev => {
      const newSet = new Set(prev);
      newSet.delete(nodeId);
      console.log('Updated expandedNodes:', Array.from(newSet));
      return newSet;
    });
    
    setNodeExpansions(prev => {
      const newMap = new Map(prev);
      newMap.delete(nodeId);
      console.log('Updated nodeExpansions:', Array.from(newMap.entries()));
      return newMap;
    });
    
    console.log('=== COLLAPSE FUNCTION END ===');
  };

  // Function to toggle node expansion with debouncing
  const toggleNodeExpansion = useCallback((nodeData) => {
    console.log('toggleNodeExpansion called for:', nodeData.elementId);
    console.log('Current state:', {
      expandedNodes: Array.from(expandedNodes),
      hasExpandable: hasExpandableConnections(nodeData),
      canCollapse: canCollapseNode(nodeData),
      isLoading: loadingNodes.has(nodeData.elementId)
    });
    
    // Prevent multiple rapid clicks
    if (loadingNodes.has(nodeData.elementId)) {
      console.log('Node is loading, skipping...');
      return;
    }
    
    if (expandedNodes.has(nodeData.elementId)) {
      console.log('Node is expanded, attempting to collapse...');
      collapseNode(nodeData.elementId);
    } else if (hasExpandableConnections(nodeData)) {
      console.log('Node can be expanded, attempting to expand...');
      expandNode(nodeData.elementId);
    } else {
      console.log('Node cannot be expanded or collapsed');
    }
  }, [expandedNodes, loadingNodes, data.nodes, searchQuery]);

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
    console.log('=== D3 RENDER EFFECT START ===');
    console.log('Filtered data:', {
      nodeCount: filteredData.nodes.length,
      linkCount: filteredData.links.length,
      sampleNode: filteredData.nodes[0],
      sampleLink: filteredData.links[0]
    });
    
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
          .attr("fill", '#666'); // Generic arrow color
 
      console.log('D3 SVG and Arrowhead Marker initialized.');
    }


 
    if (filteredData.nodes.length === 0) {
      console.log('No nodes to display - clearing graph');
      gRef.current.selectAll('*').remove();
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
      console.log('Graph cleared due to no nodes.');
      return;
    }

    console.log('Proceeding with', filteredData.nodes.length, 'nodes and', filteredData.links.length, 'links');

    // Initialize positions for new nodes (especially for search results)
    initializeNodePositions(filteredData.nodes, width, height);

    // --- Process links for bidirectional relationship separation ---
    let processedLinks = [];
    try {
      processedLinks = processLinksForOffset([...filteredData.links]);
      console.log('Successfully processed links for offset:', processedLinks.length);
    } catch (error) {
      console.error('Error processing links:', error);
      processedLinks = [...filteredData.links]; // Fallback to original links
    }

    // --- Initialize/Update Simulation ---
    if (!simulationRef.current) {
      simulationRef.current = d3.forceSimulation(filteredData.nodes)
        .force('link', d3.forceLink(processedLinks).id(d => d.elementId || JSON.stringify(d)).distance(LINK_DISTANCE))
        .force('charge', d3.forceManyBody().strength(CHARGE_STRENGTH))
        .force('center', d3.forceCenter(width / 2, height / 2).strength(CENTER_FORCE_STRENGTH))
        .force('collide', d3.forceCollide().radius(COLLIDE_RADIUS))
        .force('boundary', boundaryForce(width, height));
      console.log('D3 Simulation initialized with nodes:', filteredData.nodes.length, 'links:', processedLinks.length);
    } else {
      simulationRef.current.nodes(filteredData.nodes);
      simulationRef.current.force('link').links(processedLinks); 
      simulationRef.current.force('center', d3.forceCenter(width / 2, height / 2).strength(CENTER_FORCE_STRENGTH));
      simulationRef.current.force('boundary', boundaryForce(width, height));
      simulationRef.current.alpha(1).restart();
      console.log('D3 Simulation updated with nodes:', filteredData.nodes.length, 'links:', processedLinks.length);
    }
 
    // --- D3 Data Binding and Drawing ---
    // Links (paths for curved bidirectional links, lines for single links)
    const link = gRef.current.selectAll('.link')
      .data(processedLinks, d => d.elementId || JSON.stringify(d))
      .join(
        enter => {
          const group = enter.append('path')
            .attr('class', 'link')
            .attr('stroke', d => {
              const color = getLinkColor(d.type || 'Unknown');
              return color;
            })
            .attr('stroke-opacity', LINK_OPACITY)
            .attr('stroke-width', LINK_STROKE_WIDTH)
            .attr('fill', 'none')  // Important for path elements
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
        update => {
          // Update link color dynamically
          update.attr('stroke', d => {
            const color = getLinkColor(d.type || 'Unknown');
            return color;
          });
          return update;
        },
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
      .data(filteredData.nodes, d => d.elementId || JSON.stringify(d))
      .join(
        enter => {
          const group = enter.append('g')
            .attr('class', 'node-group')
            .call(d3.drag()
              .on('start', dragstarted)
              .on('drag', dragged)
              .on('end', dragended)
            );

          // Use circular nodes with dynamic colors
          group.append('circle')
            .attr('class', 'main-circle')
            .attr('r', NODE_RADIUS)
            .attr('fill', d => {
              const color = getNodeColor(d.label || 'Unknown');
              return color;
            })
            .attr('stroke', '#fff')
            .attr('stroke-width', 2);

          // Node label text - show name property prominently
          group.append('text')
            .attr('class', 'node-label')
            .text(d => {
              const displayText = getDisplayName(d);
              console.log('Node label rendering:', {
                nodeId: d.elementId,
                originalName: d.name,
                originalLabel: d.label,
                computedDisplayText: displayText,
                fullNode: d
              });
              return displayText;
            })
            .attr('font-size', 12)
            .attr('font-weight', 'bold')
            .attr('dx', NODE_RADIUS + 5)
            .attr('dy', 3)
            .attr('fill', '#333')
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
              console.log('=== EXPAND/COLLAPSE BUTTON CLICKED ===');
              console.log('Node ID:', d.elementId);
              console.log('Can expand:', hasExpandableConnections(d));
              console.log('Can collapse:', canCollapseNode(d));
              console.log('Is expanded:', expandedNodes.has(d.elementId));
              console.log('Loading nodes:', Array.from(loadingNodes));
              console.log('Current expandedNodes state:', Array.from(expandedNodes));
              console.log('Current nodeExpansions state:', Array.from(nodeExpansions.keys()));
              
              // Direct check and call to avoid any dependency issues
              if (expandedNodes.has(d.elementId)) {
                console.log('Node is expanded - calling collapseNode directly...');
                collapseNode(d.elementId);
              } else if (!expandedNodes.has(d.elementId) && hasExpandableConnections(d)) {
                console.log('Node can be expanded - calling expandNode directly...');
                expandNode(d.elementId);
              } else {
                console.log('No action taken - node cannot be expanded or collapsed');
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

          // Main node interactions - Updated for circular nodes
          group.on('mouseover', function (event, d) {
            d3.select(this).select('.main-circle').attr('stroke', 'black').attr('stroke-width', 3);
            d3.select(tooltipRef.current).style('z-index', 12);
            d3.select(tooltipRef.current).transition().duration(200).style('opacity', 0.9);
            
            // Get display name using our robust helper
            const displayName = getDisplayName(d);
            
            d3.select(tooltipRef.current).html(
              `<strong>Name</strong>: ${displayName}<br/>` +
              `<strong>Type</strong>: ${d.label || 'N/A'}<br/>` +
              `<strong>ID</strong>: ${d.elementId || 'N/A'}<br/>` +
              // Show other direct properties (excluding technical ones)
              Object.entries(d)
                .filter(([k, v]) => !['elementId', 'id', 'label', 'name', 'x', 'y', 'vx', 'vy', 'index', 'fx', 'fy', 'properties', '_originalNode'].includes(k))
                .filter(([k, v]) => v !== null && v !== undefined && v !== '')
                .map(([k, v]) => `<strong>${k}</strong>: ${v}`).join('<br/>') +
              // Show nested properties if they exist
              (d.properties && Object.keys(d.properties).length > 0 ? 
                `<br/>--- Properties ---<br/>` +
                Object.entries(d.properties)
                  .filter(([k, v]) => v !== null && v !== undefined && v !== '')
                  .map(([k, v]) => `<strong>${k}</strong>: ${v}`).join('<br/>') : '')
            )
            .style('left', `${event.pageX + 10}px`)
            .style('top', `${event.pageY - 15}px`);
          })
          .on('mouseout', function () {
            d3.select(this).select('.main-circle').attr('stroke', '#fff').attr('stroke-width', 2);
            d3.select(tooltipRef.current).transition().duration(400).style('opacity', 0);
          });

          return group;
        },
        update => {
          // Update circle color dynamically
          update.select('.main-circle')
            .attr('fill', d => {
              const color = getNodeColor(d.label || 'Unknown');
              return color;
            });
          
          update.select('.node-label')
            .text(d => {
              const displayText = getDisplayName(d);
              return displayText;
            })
            .attr('font-size', 12)
            .attr('font-weight', 'bold')
            .attr('fill', '#333');

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
        setNodeExpansions(new Map());
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
    setNodeExpansions(new Map());
  }, [searchQuery]);
 
  return (
    <div style={{position: 'relative', marginLeft: '30px',width: '98%', height: '80vh', display: 'flex', flexDirection: 'column' }}>
      {error && (
        <div style={{
          position: 'absolute',
          top: '20px',
          left: '50%',
          transform: 'translateX(-50%)',
          backgroundColor: '#ffebee',
          color: '#c62828',
          padding: '10px 20px',
          borderRadius: '4px',
          border: '1px solid #ef5350',
          zIndex: 1000,
          maxWidth: '80%',
          textAlign: 'center'
        }}>
          <strong>Error:</strong> {error}
          <br />
          <small>Check the console for more details. The graph may not work with this database schema.</small>
        </div>
      )}
      
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
               setNodeExpansions(new Map());
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

