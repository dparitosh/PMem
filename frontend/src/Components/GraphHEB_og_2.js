import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import * as d3 from 'd3';
import neo4j from 'neo4j-driver';
import '../CSS/GraphHEB.css';
import axios from 'axios';

// Performance: Disable excessive console logging in production
const isDevelopment = process.env.NODE_ENV === 'development';
const performanceLog = isDevelopment ? console.log : () => {};
const performanceWarn = isDevelopment ? console.warn : () => {};

// Performance: Create a single axios instance with optimized defaults
const apiClient = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  timeout: 10000, // 10 second timeout
  headers: {
    'Content-Type': 'application/json',
  }
});

// Performance: Add request/response interceptors for caching
const requestCache = new Map();
apiClient.interceptors.request.use((config) => {
  if (config.method === 'get') {
    const cacheKey = config.url + JSON.stringify(config.params);
    if (requestCache.has(cacheKey)) {
      return Promise.reject({ cached: true, data: requestCache.get(cacheKey) });
    }
  }
  return config;
});

apiClient.interceptors.response.use((response) => {
  if (response.config.method === 'get') {
    const cacheKey = response.config.url + JSON.stringify(response.config.params);
    requestCache.set(cacheKey, response.data);
    // Cache for 5 minutes
    setTimeout(() => requestCache.delete(cacheKey), 300000);
  }
  return response;
}, (error) => {
  if (error.cached) {
    return Promise.resolve({ data: error.data });
  }
  return Promise.reject(error);
});
 
// Initialize Neo4j Driver once outside the component.
const driver = neo4j.driver(
//   'bolt://localhost:7687',
  'bolt://localhost:7687',
  neo4j.auth.basic('neo4j', 'pwd'),
   { disableLosslessIntegers: true }
);
 
// Define constants for D3 parameters and styling
const NODE_ACTIVE_COLOR = '#6C757D';
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
 
const GraphHEB = ({ setData, setSearchResults, showChat, toggleChat, setActiveTab }) => {
  const svgRef = useRef();
  const tooltipRef = useRef();
  const relationTooltipRef = useRef();
 
  const simulationRef = useRef(null);
  const gRef = useRef(null); // Ref for the main D3 group element

  // Performance: Optimize state management
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [filteredData, setFilteredData] = useState({ nodes: [], links: [] });
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  // Performance: Add loading states for better UX
  const [isSearching, setIsSearching] = useState(false);
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
  const [dataVersion, setDataVersion] = useState(0); // Track data changes
  // Comparative search state
  const [showComparativeSearch, setShowComparativeSearch] = useState(false);
  const [compareSearchLoading, setCompareSearchLoading] = useState({ left: false, right: false });
  const [compareSearchResults, setCompareSearchResults] = useState({ left: null, right: null });
  const [compareSearchInputs, setCompareSearchInputs] = useState({
    left: { nodeType: '', name: '', version: '' },
    right: { nodeType: '', name: '', version: '' }
  });
  const [comparisonData, setComparisonData] = useState(null);
  // Unified primary button color (match WhereUsedView request)
  const primaryButtonColor = 'rgb(10, 130, 118)';
  // New keyword-based dual-node comparison (graphfilter) states
  const [compareTermA, setCompareTermA] = useState('');
  const [compareTermB, setCompareTermB] = useState('');
  const [compareResultsA, setCompareResultsA] = useState([]); // results from /graphfilter for Node A
  const [compareResultsB, setCompareResultsB] = useState([]); // results from /graphfilter for Node B
  const [selectedCompareNodeA, setSelectedCompareNodeA] = useState(null);
  const [selectedCompareNodeB, setSelectedCompareNodeB] = useState(null);
  const [isCompareSearching, setIsCompareSearching] = useState({ A: false, B: false });
  const [propertyComparisonData, setPropertyComparisonData] = useState(null); // full property union diff
  // Performance: Debounced search query
  const debouncedSearchQuery = useDebounce(searchQuery, 300); // 300ms delay
  // Performance: Memoized search function
  const nodeSearchFunction = useMemo(() => createNodeSearchFunction(), []);
  
  // Comparative search API function
  const performComparativeSearch = useCallback(async (nodeType, name, version) => {
    try {
      const response = await apiClient.post('/comparative-search', {
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
      console.error('Comparative search error:', error);
      throw error;
    }
  }, []);
  
  // Performance: Memoized color mapping - GENERIC VERSION
  const getNodeColor = useCallback((label) => {
    if (!label) return '#808080'; // Gray fallback for undefined labels
    
    // Generate consistent color based on label hash
    const hash = label.split('').reduce((a, b) => {
      a = ((a << 5) - a) + b.charCodeAt(0);
      return a & a;
    }, 0);
    
    // Convert hash to HSL color for better color distribution
    const hue = Math.abs(hash) % 360;
    const saturation = 70; // Fixed saturation for consistency
    const lightness = 50; // Lightness for better visibility
    
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  }, []);

  // Generic color function for link types
  const getLinkColor = useCallback((linkType) => {
    if (!linkType) return '#999999';
    
    // Generate consistent color based on link type hash
    const hash = linkType.split('').reduce((a, b) => {
      a = ((a << 5) - a) + b.charCodeAt(0);
      return a & a;
    }, 0);
    
    // Convert hash to HSL color
    const hue = Math.abs(hash) % 360;
    const saturation = 60;
    const lightness = 60;
    
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
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

    console.log(`Creating hierarchical data from ${nodes.length} nodes and ${links.length} links`);

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
    
    // Count incoming connections for each node
    links.forEach(link => {
      const rawSource = typeof link.source === 'object' ? (link.source.elementId || link.source.id || link.source.identity) : link.source;
      const rawTarget = typeof link.target === 'object' ? (link.target.elementId || link.target.id || link.target.identity) : link.target;
      const sourceId = getNodeId({ elementId: rawSource });
      const targetId = getNodeId({ elementId: rawTarget });
      
      // Find the actual nodes to check their types and relationship types
      const sourceNode = nodes.find(n => getNodeId(n) === sourceId);
      const targetNode = nodes.find(n => getNodeId(n) === targetId);
      const relationshipType = link.type || link.properties?.type;
      
      console.log(`[Hierarchy] Processing link: ${sourceNode?.labels?.[0] || 'unknown'}(${sourceId?.substring(0,8)}) -> ${targetNode?.labels?.[0] || 'unknown'}(${targetId?.substring(0,8)}) [${relationshipType}]`);
      
      // Enhanced relationship logic based on types and relationship direction
      if (sourceNode && targetNode) {
        const sourceLabel = sourceNode.labels?.[0] || sourceNode.label;
        const targetLabel = targetNode.labels?.[0] || targetNode.label;
        
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
          console.log(`[Hierarchy] Set parent: ${parentId?.substring(0,8)} -> child: ${childId?.substring(0,8)}`);
        }
      } else {
        // Fallback to normal relationship if nodes not found
        incomingConnections.set(targetId, (incomingConnections.get(targetId) || 0) + 1);
        outgoingConnections.set(sourceId, (outgoingConnections.get(sourceId) || 0) + 1);
      }
    });
    
    // Debug: Show connection counts for a few nodes
    const debugNodes = Array.from(incomingConnections.entries()).slice(0, 5);
    console.log('Sample incoming connections:', debugNodes);
    
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
      
      console.log(`Expanded dataset: Using ${roots.length} roots from ${expandedNodeIds.length} expanded nodes`);
    } else {
      // Original logic for non-expanded datasets: find nodes with no incoming connections
      roots = nodes.filter(node => !incomingConnections.has(node.elementId));
    }
    
    console.log(`Nodes with no incoming connections: ${roots.length}`);
    
    // If no clear roots, pick all nodes with lowest incoming connections
    if (roots.length === 0) {
      const minConnections = Math.min(...Array.from(incomingConnections.values()));
      roots = nodes.filter(node => 
        (incomingConnections.get(node.elementId) || 0) === minConnections
      );
      console.log(`No clear roots found, using ${roots.length} nodes with minimum connections (${minConnections})`);
    }
    
    // Still no roots? Just use all nodes as roots
    if (roots.length === 0) {
      roots = [...nodes];
      console.log(`No roots found at all, treating all ${nodes.length} nodes as roots`);
    }
    
    console.log(`Found ${roots.length} root nodes`);
    
    // Build hierarchy from roots
    const processedNodes = new Set();
    const hierarchy = [];
    
    const buildNodeHierarchy = (node, level = 0, visited = new Set()) => {
      if (!node || !node.elementId) {
        console.warn('[Hierarchy] Invalid node passed to buildNodeHierarchy:', node);
        return null;
      }
      
      if (visited.has(node.elementId)) {
        console.warn(`[Hierarchy] Circular reference detected for node ${node.elementId?.substring(0,8)} at level ${level}, breaking cycle`);
        return null;
      }
      
      if (level > 10) {
        console.warn(`[Hierarchy] Maximum depth exceeded for node ${node.elementId?.substring(0,8)}`);
        return null;
      }
      
      visited.add(node.elementId);
      processedNodes.add(node.elementId);
      
      const nodeLabel = node.labels?.[0] || node.label;
      
      // Find children of this node using explicit relationship rules
      let children = links
        .filter(link => {
          const rawSource = typeof link.source === 'object' ? (link.source.elementId || link.source.id || link.source.identity) : link.source;
          const rawTarget = typeof link.target === 'object' ? (link.target.elementId || link.target.id || link.target.identity) : link.target;
          const sourceId = getNodeId({ elementId: rawSource });
          const targetId = getNodeId({ elementId: rawTarget });
          const relationshipType = link.type || link.properties?.type;
          
          const sourceNode = nodes.find(n => getNodeId(n) === sourceId);
          const targetNode = nodes.find(n => getNodeId(n) === targetId);
          
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
          
          return nodes.find(n => getNodeId(n) === childId);
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
        // Ensure properties exist
        properties: node.properties || {},
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
        console.log(`Built hierarchy for root ${root.elementId?.substring(0,8)} with ${tree.children?.length || 0} children`);
      }
    });
    
    // For expansions, reorganize hierarchy to ensure proper parent-child relationships without duplicates
    if (expandedNodes.size > 0 && hierarchy.length > 0) {
      console.log(`[Hierarchy] Reorganizing ${hierarchy.length} trees for ${expandedNodes.size} expanded nodes`);
      
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
          console.log(`[Hierarchy] Root ${containingRoot.elementId?.substring(0,8)} contains expanded node ${expandedNodeId?.substring(0,8)}`);
        }
      });
      
      // Add any roots that weren't processed but should be included
      hierarchy.forEach(root => {
        if (!processedRootIds.has(root.elementId)) {
          updatedRoots.push(root);
          console.log(`[Hierarchy] Including additional root ${root.elementId?.substring(0,8)}`);
        }
      });
      
      // Replace hierarchy with reorganized roots
      hierarchy.length = 0;
      hierarchy.push(...updatedRoots);
      console.log(`[Hierarchy] Reorganized to ${hierarchy.length} root trees`);
    }
    
    // Add any orphaned nodes at the end
    const orphans = nodes.filter(node => !processedNodes.has(node.elementId));
    console.log(`Adding ${orphans.length} orphaned nodes`);
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
    console.log(`Final hierarchy has ${hierarchy.length} top-level nodes; outgoing-without-children (pre-orphans): ${nodesWithoutChildrenButOutgoing}; inputUniqueIds=${inputIdCount}; hierarchyTotalUniqueIds=${hierarchyAllIds.size}`);
    return hierarchy;
  }, []);  // Remove dependencies that cause infinite loops

  // Function to compare two node hierarchies and find differences
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
      const response = await apiClient.post('/graphfilter', { search: trimmed.toLowerCase() });
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
      console.error('Keyword comparison search failed', e);
      if (side === 'A') setCompareResultsA([]); else setCompareResultsB([]);
    } finally {
      setIsCompareSearching(prev => ({ ...prev, [side]: false }));
    }
  }, [apiClient]);

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
  }, [selectedCompareNodeA, selectedCompareNodeB]);

  const exportComparisonCSV = () => {
    if (!propertyComparisonData) return;
    const lines = [];
    lines.push(['Property','Node A','Node B','Status'].join(','));
    propertyComparisonData.rows.forEach(r => {
      const esc = (v) => {
        if (v == null) return '';
        const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
        return '"' + s.replace(/"/g,'""') + '"';
      };
      lines.push([r.property, esc(r.left), esc(r.right), r.status].join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const baseNameA = getNodeShortLabel(propertyComparisonData.nodeA).replace(/[^a-z0-9_-]+/gi,'_');
    const baseNameB = getNodeShortLabel(propertyComparisonData.nodeB).replace(/[^a-z0-9_-]+/gi,'_');
    a.download = `node_comparison_${baseNameA}_vs_${baseNameB}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Reset property comparison when selection changes
  useEffect(()=> { setPropertyComparisonData(null); }, [selectedCompareNodeA, selectedCompareNodeB]);
  
  // Handle comparative search for a specific side
  const handleComparativeSearch = useCallback(async (side) => {
    const inputs = compareSearchInputs[side];
    
    if (!inputs.nodeType || !inputs.name) {
      alert('Please fill in Node Type and Name fields');
      return;
    }
    
    setCompareSearchLoading(prev => ({ ...prev, [side]: true }));
    
    try {
      const results = await performComparativeSearch(inputs.nodeType, inputs.name, inputs.version);
      setCompareSearchResults(prev => {
        const newResults = { ...prev, [side]: results };
        
        // If both sides now have results, perform comparison
        const otherSide = side === 'left' ? 'right' : 'left';
        if (newResults.left && newResults.right && newResults.left.nodes.length > 0 && newResults.right.nodes.length > 0) {
          setTimeout(() => {
            const comparison = compareNodeHierarchies(newResults.left, newResults.right);
            setComparisonData(comparison);
          }, 100);
        }
        
        return newResults;
      });
      
    } catch (error) {
      console.error(`Comparative search failed for ${side}:`, error);
      alert(`Search failed: ${error.message}`);
    } finally {
      setCompareSearchLoading(prev => ({ ...prev, [side]: false }));
    }
  }, [compareSearchInputs, performComparativeSearch, compareNodeHierarchies]);
  
  // Handle input changes for comparative search
  const handleCompareInputChange = useCallback((side, field, value) => {
    setCompareSearchInputs(prev => ({
      ...prev,
      [side]: {
        ...prev[side],
        [field]: value
      }
    }));
  }, []);

  // Unified display label helper (name + external/version when present)
  const getDisplayLabel = useCallback((node) => {
    if (!node) return 'Unknown';
    const props = node.properties || node;
    
    // Generic: try common name properties
    const primaryName = props.name || props.title || props.code || props.key || props.number || props.abbreviation || 'Unknown';
    
    // Version precedence: external_version then version
    const version = props.external_version || props.version;
    if (version) return `${primaryName} (v${version})`;
    return primaryName;
  }, []);

  // Primary label logic used in BOTH force-directed graph and indented tree for perfect parity
  const getPrimaryNodeLabel = useCallback((d) => {
    if (!d) return 'Unknown';
    
    // Generic approach: try common name/title properties first
    const props = d.properties || d;
    const name = props.name || props.title || props.abbreviation || props.key || props.code || d.name || d.title;
    
    // Try to add version if available (comma style for consistency)
    const version = props.external_version || props.version || d.external_version || d.version;
    if (name && version) return `${name}, ${version}`;
    if (name) return name;
    
    // Ultimate fallback
    return d.label || props.label || 'Unknown';
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

    console.log(`Rendering indented tree with ${data.nodes.length} nodes`);

    // Disable zoom for tree layout
    svg.on('.zoom', null);

    let hierarchicalData = createHierarchicalData(data.nodes, data.links || []);

    // Improved fallback: if filtered (current) dataset has zero links (common after search)
    // build hierarchy ONLY over the currently visible nodes using matching links from fullDataset.
    if ((data.links?.length || 0) === 0 && (fullDataset?.links?.length || 0) > 0 && (data.nodes?.length || 0) > 0) {
      console.log('[TreeLayout] Building subset hierarchy from fullDataset links filtered to current nodes.');
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
      console.log('[TreeLayout] Rebuilding hierarchy after expansion with relationship data');
      hierarchicalData = createHierarchicalData(data.nodes, data.links);
    }
    try {
      const nodesWithChildren = hierarchicalData.reduce((acc, r) => acc + ((r.children && r.children.length) ? 1 : 0), 0);
      const totalDescChildren = (function countAll(nodes){
        return nodes.reduce((acc,n)=> acc + (n.children? n.children.length : 0) + (n.children? countAll(n.children):0),0);
      })(hierarchicalData);
      console.log('[TreeLayout] Roots:', hierarchicalData.length, 'RootsWithChildren:', nodesWithChildren, 'Total descendant links:', totalDescChildren);
    } catch(e) {
      console.warn('[TreeLayout] Debug metrics failed', e);
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
        console.warn('[TreeLayout] flattenHierarchy received non-array nodes:', nodes);
        return result;
      }
      
      nodes.forEach(node => {
        if (!node || !node.elementId) {
          console.warn('[TreeLayout] Skipping invalid node:', node);
          return;
        }
        
        // Skip if we've already seen this node to prevent duplicates and infinite loops
        if (seenIds.has(node.elementId)) {
          console.warn(`[TreeLayout] Skipping duplicate node: ${node.elementId?.substring(0,8)}`);
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
    console.log('[TreeLayout] Hierarchy structure:');
    hierarchicalData.forEach((root, idx) => {
      console.log(`Root ${idx}: ${root.elementId?.substring(0,8)} (${root.labels?.[0]}) - level ${root.level}`);
      const logChildren = (node, indent = '  ') => {
        if (node.children && node.children.length > 0) {
          node.children.forEach(child => {
            console.log(`${indent}Child: ${child.elementId?.substring(0,8)} (${child.labels?.[0]}) - level ${child.level}`);
            logChildren(child, indent + '  ');
          });
        }
      };
      logChildren(root);
    });
    
    // Debug: log flattened nodes with levels to verify they're being set correctly
    console.log('[TreeLayout] Flattened nodes with levels:', flatNodes.slice(0, 8).map(n => ({
      id: n.elementId?.substring(0, 8) + '...', 
      level: n.level, 
      label: n.labels?.[0] || 'unknown',
      expanded: treeExpandedNodes.has(n.elementId),
      isRoot: n.level === 0
    })));
    
    // Ensure all root nodes are always visible
    const rootsInFlattened = flatNodes.filter(n => n.level === 0);
    console.log(`[TreeLayout] Root nodes in flattened: ${rootsInFlattened.length} of ${hierarchicalData.length} total roots`);
    
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
        console.log(`[TreeLayout][Parity] Missing ${missing.length} nodes in flattened view (sample up to 15):`, missing.slice(0,15).map(n => n.elementId));
      }

      // If the hierarchy covers every unique node (even if duplicates exist due to DAG), auto-expand all
      if (allIdsSet.size === data.nodes.length) {
        console.log('[TreeLayout][Parity] Auto-expanding all nodes to achieve parity.');
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
        console.log(`[TreeLayout][Parity] Hierarchy unique coverage (${allIdsSet.size}) != data.nodes (${data.nodes.length}); not auto-expanding.`);
      }
    }
    console.log(`Flattened hierarchy has ${flatNodes.length} nodes (target ${data.nodes.length})`);
    
    const rowHeight = 40;
    const indentWidth = 30;
    const nodeSize = 12;
    const headerHeight = 60;

    // Defensive: some layouts report svg clientHeight = 0 (e.g., flex container without explicit height)
    let effectiveHeight = height && height > (headerHeight + 40) ? height : 600; // fallback
    if (height <= (headerHeight + 40)) {
      console.warn('[TreeLayout][HeightFallback] SVG height was', height, 'using fallback', effectiveHeight);
    }

    // Calculate total height needed
    const totalContentHeight = flatNodes.length * rowHeight;
    let availableHeight = effectiveHeight - headerHeight - 20; // Leave margin
    if (availableHeight <= 0) {
      availableHeight = Math.min(560, totalContentHeight + 40); // safety
      console.warn('[TreeLayout][HeightFallback] Computed availableHeight <= 0; adjusted to', availableHeight);
    }
    const containerHeight = Math.min(availableHeight, totalContentHeight);
    console.log(`[TreeLayout][Dims] width=${width} rawHeight=${height} effectiveHeight=${effectiveHeight} availableHeight=${availableHeight} containerHeight=${containerHeight} totalContentHeight=${totalContentHeight}`);
    
    const g = gRef.current;
    g.attr('transform', 'translate(0, 0)'); // Reset transform for tree layout
    
    // Add background
    g.append('rect')
      .attr('width', width - 40)
      .attr('height', containerHeight)
      .attr('fill', '#fafafa')
      .attr('stroke', '#ddd')
      .attr('rx', 5);
    
    // Add header with corporate styling
    const headerGroup = g.append('g');
    
    // Header background
    headerGroup.append('rect')
      .attr('width', width - 40)
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
      .text(`� Hierarchical Data View`);
    
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
      console.warn('[TreeLayout][Debug] Clip path disabled; content may overflow.');
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
      console.log('[TreeLayout][RenderRows] Rendering', flatNodes.length, 'rows; offset=', offset);

      rows.append('rect')
        .attr('width', width - 40)
        .attr('height', rowHeight - 2)
        .attr('x', 20)
        .attr('fill', (d, i) => i % 2 === 0 ? '#fdfdfd' : '#f8f9fa')
        .attr('stroke', '#c3d4e6')
        .attr('rx', 3)
        .style('cursor', 'pointer')
        .on('click', function(event, d) {
          console.log('Tree node clicked:', d);
        })
        .on('mouseover', function(event, d) {
          d3.select(this)
            .attr('fill', '#f1f3f4')
            .attr('stroke', '#6c757d')
            .attr('stroke-width', 1);
        })
        .on('mouseout', function(event, d) {
          d3.select(this)
            .attr('fill', (_, i) => i % 2 === 0 ? '#fdfdfd' : '#f8f9fa')
            .attr('stroke', '#dee2e6')
            .attr('stroke-width', 1);
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
      console.log('[TreeLayout] Expandable row count:', expandable.size());

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
              if (canCollapseNode(d)) return '−'; // Minus for collapse
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
        // Show actual node name and version, not just the label type
        const props = d.properties || d;
        
        // Generic: try common name properties
        const nodeName = props.name || props.title || props.abbreviation || props.code || props.key || props.number ||
                        d.name || d.title || d.label || d.id || d.elementId || 'Unknown';
        
        const version = props.external_version || props.version || d.version || d.external_version;
        
        const primaryLabel = version ? `${nodeName} (v${version})` : nodeName;
        
        // Check if text needs wrapping (if longer than available space)
        const availableWidth = width - mainLabelX - 100; // Leave space for expand buttons
        
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

            return parts.join(' • ');
          });
      });

      // Debug overlay removed (previous #tree-debug-fallback). Intentionally left blank.

      return rows;
    };

    // Initial render
    const rows = renderRows(scrollOffset);

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
    
  }, [createHierarchicalData, tooltipRef, treeExpandedNodes, fullDataset, getDisplayLabel]);

  // Effect to handle tree layout updates when data changes from expansions
  useEffect(() => {
    if (layoutType === 'indented-tree' && expandedNodes.size > 0) {
      console.log('[TreeLayout] Data changed with expanded nodes, updating tree state');
      
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
          console.log('Filtering out HAS_PARENT link as HAS_CHILD exists for the same node pair:', pairKey);
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
      
      console.log(`🔄 Layout switching from ${layoutType} to ${newLayoutType}`);
      
      // Stop current simulation immediately for smooth transition
      if (simulationRef.current && newLayoutType === 'indented-tree') {
        simulationRef.current.stop();
        simulationRef.current = null;
      }
      
      setLayoutType(newLayoutType);
      
      // Ensure we have the full dataset available for both layouts
      if (newLayoutType === 'force-directed') {
        // For graph layout, use full dataset
        console.log(`🎨 Restoring full dataset for graph layout: ${graphData.nodes?.length || 0} nodes`);
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
          console.log(`🌲 Tree layout initialized with ${currentNodes.length} nodes, ${rootIds.length} roots`);
        } catch (e) {
          console.warn('Tree expansion init failed', e);
        }
      }
      
      // Performance monitoring
      requestAnimationFrame(() => {
        const endTime = performance.now();
        console.log(`Layout switch completed in ${(endTime - startTime).toFixed(2)}ms`);
        setIsLayoutSwitching(false);
      });
    }
  }, [layoutType, graphData, createHierarchicalData]);

  // Throttled simulation tick to improve performance
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
      console.log('🔄 Starting data fetch from API...');
      setIsLoading(true);
      setError(null);
      
      try {
        console.log('📡 Making API call to /graphvis...');
        const response = await apiClient.get('/graphvis');
        console.log('API Response received:', {
          status: response.status,
          dataExists: !!response.data,
          resultsCount: response.data?.results?.length || 0,
          firstResult: response.data?.results?.[0]
        });
        
        // Process initial data directly
        if (response.data?.results?.length > 0) {
          console.log('🔍 Processing API data...');
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
          
          console.log(`✅ Data processed successfully: ${nodes.length} nodes, ${validatedLinks.length} links`);
          
          // Set all data states consistently
          const dataSet = { nodes, links: validatedLinks };
          setData(dataSet);
          setGraphData(dataSet);
          setFilteredData(dataSet);
          setFullDataset(dataSet);
          setInitialData(dataSet);
        } else {
          console.log('No results in API response or empty results array');
        }
        
        setIsLoading(false);
      } catch (err) {
        console.error('❌ Data Fetch Error:', err);
        console.error('Error details:', {
          message: err.message,
          response: err.response?.data,
          status: err.response?.status
        });
        setError(`Failed to load graph data: ${err.message}`);
        setIsLoading(false);
      }
    };

    fetchData();
  }, []);
 
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
      setIsSearching(false);
      setSearchLoading(false);
      return;
    }

    const performSearch = async () => {
      console.log('🔍 Starting search for:', debouncedSearchQuery);
      setIsSearching(true);
      setSearchLoading(true);
      
      try {
        const response = await apiClient.post('/graphfilter', {
          search: debouncedSearchQuery.toLowerCase()
        });
        
        console.log('🔍 Search API response:', response.data?.results?.length || 0, 'results');
        if (response.data?.results?.length > 0) {
          console.log('🔍 First result structure:', JSON.stringify(response.data.results[0], null, 2));
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
          
          console.log('🔍 Search processed:', nodes.length, 'nodes,', validatedLinks.length, 'links');
          
          // For search results, REPLACE existing data instead of merging
          // This prevents contamination from previous searches or expansions
          let finalNodes = nodes;
          let finalLinks = validatedLinks;
          
          // Only preserve expansion data if the expanded nodes are part of current search results
          if (expandedNodes.size > 0) {
            console.log('🔍 Checking expanded nodes for relevance to current search');
            const searchNodeIds = new Set(nodes.map(n => n.elementId));
            const relevantExpansions = new Set();
            
            // Only keep expansions where the original expanded node is in current search
            for (const expandedNodeId of expandedNodes) {
              if (searchNodeIds.has(expandedNodeId)) {
                relevantExpansions.add(expandedNodeId);
                console.log('🔍 Keeping expansion for:', expandedNodeId);
              } else {
                console.log('🔍 Removing irrelevant expansion for:', expandedNodeId);
              }
            }
            
            // Update expansion tracking to only relevant ones
            setExpandedNodes(relevantExpansions);
            const updatedNodeExpansions = new Map();
            for (const nodeId of relevantExpansions) {
              if (nodeExpansions.has(nodeId)) {
                updatedNodeExpansions.set(nodeId, nodeExpansions.get(nodeId));
              }
            }
            setNodeExpansions(updatedNodeExpansions);
          }
          
          console.log('Setting filteredData with:', finalNodes.length, 'nodes,', finalLinks.length, 'links');
          setFilteredData({ nodes: finalNodes, links: finalLinks });
          
          // Update search results for other components
          if (setSearchResults) {
            setSearchResults(finalNodes);
          }
        } else {
          // No results found
          console.log('🔍 No search results found for:', debouncedSearchQuery);
          setFilteredData({ nodes: [], links: [] });
          // Update search results to empty array for other components
          if (setSearchResults) {
            setSearchResults([]);
          }
        }
        
        setIsSearching(false);
        setSearchLoading(false);
      } catch (err) {
        console.error('Search Error:', err);
        // Fallback to client-side search if server search fails
        // Use fullDataset to include expanded nodes in search
        const searchData = fullDataset.nodes.length > 0 ? fullDataset : graphData;
        const filteredNodes = nodeSearchFunction(searchData.nodes, debouncedSearchQuery);
        const filteredNodeIds = new Set(filteredNodes.map(n => n.elementId));
        const filteredLinks = searchData.links.filter(
          l => filteredNodeIds.has(l.source?.elementId || l.source) && 
               filteredNodeIds.has(l.target?.elementId || l.target)
        );
        setFilteredData({ nodes: filteredNodes, links: filteredLinks });
        // Update search results for other components  
        if (setSearchResults) {
          setSearchResults(filteredNodes);
        }
        setIsSearching(false);
        setSearchLoading(false);
      }
    };

    performSearch();
  }, [debouncedSearchQuery, nodeSearchFunction]); // Removed graphData dependency

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
      const response = await axios.get(`http://127.0.0.1:8000/graphtraverse/${nodeId}`);
      
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
                console.log('Added direct connection:', connectedNodeId);
              }
            }
          }
        });
        
        const finalNodes = Array.from(newNodesMap.values());
        const finalLinks = Array.from(newLinksMap.values());
        
        console.log('One-level expansion:', addedNodeIds.size, 'new nodes,', addedLinkIds.size, 'new links');
        
        // Validate links
        const existingNodeIds = new Set(finalNodes.map(node => node.elementId));
        const validatedLinks = finalLinks.filter(link => 
          existingNodeIds.has(link.source) && existingNodeIds.has(link.target)
        );
        
        // Update the current filtered data (what's currently displayed)
        setFilteredData({ nodes: finalNodes, links: validatedLinks });
        
        // ONLY update fullDataset if we're NOT in a search state
        // This prevents reverting to default nodes when expanding during search
        if (!debouncedSearchQuery) {
          setFullDataset({ nodes: finalNodes, links: validatedLinks });
          setData({ nodes: finalNodes, links: validatedLinks });
          setGraphData({ nodes: finalNodes, links: validatedLinks });
        }
        
        // Update search results if search is active
        if (setSearchResults && debouncedSearchQuery) {
          setSearchResults(finalNodes);
        }
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
      
    } catch (error) {
      console.error('Error expanding node:', nodeId, error);
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
    setData(newData);
    setGraphData(newData);
    if (setSearchResults) {
      setSearchResults(newData.nodes);
    }
    
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
  }, [expandedNodes, loadingNodes, graphData.nodes, searchQuery]);

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
    console.log(`🎨 Starting render with ${filteredData.nodes?.length || 0} nodes, ${filteredData.links?.length || 0} links`);
    
    // Performance optimization: detect layout changes
    const layoutChanged = layoutType !== prevLayoutType;
    if (layoutChanged) {
      console.log(`🔄 Layout changed from ${prevLayoutType} to ${layoutType}`);
      setPrevLayoutType(layoutType);
      setDataVersion(prev => prev + 1);
    }
    
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
          .attr("fill", LINK_COLOR || '#999'); // Fill color of the arrow

      console.log('D3 SVG and Arrowhead Marker initialized.');
    }

    // Check if we have data to render - use full dataset if filteredData is empty and we have graphData
    const hasData = filteredData.nodes.length > 0 || (graphData.nodes && graphData.nodes.length > 0);
    const renderData = filteredData.nodes.length > 0 ? filteredData : 
                      (graphData.nodes && graphData.nodes.length > 0) ? graphData : 
                      { nodes: [], links: [] };

    if (!hasData) {
      gRef.current.selectAll('*').remove();
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
      console.log('No nodes to display after filtering. Graph cleared.');
      return;
    }

    console.log(`Rendering with ${renderData.nodes.length} nodes, ${renderData.links.length} links`);
    
    // Performance warning for large graphs
    if (renderData.nodes.length > 500) {
      console.warn(`Large graph detected (${renderData.nodes.length} nodes). Performance may be affected.`);
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
        gRef.current.selectAll('*').remove();
      }
      // Render indented tree layout using the correct data
      console.log(`🌳 Rendering tree with ${renderData.nodes.length} nodes`);
      renderIndentedTree(renderData, svg, width, height);
      console.log('Rendered Indented Tree Layout');
      return;
    }

    // Force-directed layout (original code)
    // Clear tree layout content and ensure proper group structure
    if (gRef.current) {
      gRef.current.selectAll('*').remove();
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
    
    console.log(`Initializing graph layout with ${renderData.nodes.length} nodes, ${renderData.links.length} links`);
    
    // Initialize positions for new nodes (especially for search results)
    initializeNodePositions(renderData.nodes, width, height);

    // --- Process links for bidirectional relationship separation ---
    const processedLinks = processLinksForOffset([...renderData.links]);

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
      
      console.log('D3 Simulation initialized with', nodeCount, 'nodes');
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
        console.log(`D3 Simulation updated with alpha ${alpha} (nodes changed: ${nodesChanged}, layout changed: ${layoutChanged})`);
      } else {
        console.log('Skipping simulation update - no data changes detected');
      }
    }
 
    // --- D3 Data Binding and Drawing ---
    // Links (paths for curved bidirectional links, lines for single links)
    const link = gRef.current.selectAll('.link')
      .data(processedLinks, d => d.elementId)
      .join(
        enter => {
          const group = enter.append('path')
            .attr('class', 'link')
            .attr('stroke', LINK_COLOR || '#999')
            .attr('stroke-opacity', LINK_OPACITY)
            .attr('stroke-width', LINK_STROKE_WIDTH)
            .attr('fill', 'none')  // Important for path elements
            .attr('marker-end', 'url(#arrowhead)')
            .on('mouseover', function (event, d) {
              d3.select(relationTooltipRef.current).style('z-index', 12);
              d3.select(relationTooltipRef.current).style('opacity', 0.9);
              
              // Create corporate-standard relationship tooltip
              const relationshipType = d.type || 'Unknown Relationship';
              const props = d.properties || {};
              
              let tooltipContent = `
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #feca57 100%); color: white; padding: 8px 12px; margin: -8px -8px 8px -8px; font-weight: bold; border-radius: 4px 4px 0 0;">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <i class="fas fa-link" style="font-size: 16px; color: #666;"></i>
                    <span>${relationshipType}</span>
                  </div>
                </div>
              `;
              
              // Add relationship ID
              // Removed elementId display per UX requirement
              
              // Add relationship direction info using display labels if objects present
              const srcNode = typeof d.source === 'object' ? d.source : (filteredData.nodes || []).find(n => n.elementId === d.source);
              const tgtNode = typeof d.target === 'object' ? d.target : (filteredData.nodes || []).find(n => n.elementId === d.target);
              const srcLabel = getDisplayLabel(srcNode);
              const tgtLabel = getDisplayLabel(tgtNode);
              tooltipContent += `<div style="margin-bottom: 8px; font-size: 12px; color: #2C2C2C;">
                <strong>From:</strong> ${srcLabel}<br/>
                <strong>To:</strong> ${tgtLabel}
              </div>`;
              
              // Add properties if any
              if (Object.keys(props).length > 0) {
                tooltipContent += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #ecf0f1; font-size: 12px;">`;
                Object.entries(props).forEach(([k, v]) => {
                  tooltipContent += `<div style="margin: 2px 0;"><strong>${k}:</strong> ${v}</div>`;
                });
                tooltipContent += `</div>`;
              } else {
                tooltipContent += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #ecf0f1; font-size: 12px; color: #7f8c8d; font-style: italic;">No additional properties</div>`;
              }
              
              d3.select(relationTooltipRef.current).html(tooltipContent)
                .style('left', `${event.pageX + 10}px`)
                .style('top', `${event.pageY - 15}px`);
            })
          
            group.on('mouseout', () => {
              d3.select(relationTooltipRef.current).style('opacity', 0);
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
            .attr('stroke', '#6C757D')
            .attr('stroke-width', 2)
            .attr('stroke-dasharray', '5,5')
            .style('opacity', d => loadingNodes.has(d.elementId) ? 1 : 0)
            .style('pointer-events', 'none');

          // Main node interactions - Updated to handle both icon and fallback circle
          group.on('mouseover', function (event, d) {
            d3.select(this).select('.main-icon')
              .attr('stroke', 'black')
              .attr('stroke-width', 2);
            d3.select(this).select('.fallback-circle')
              .attr('stroke', 'black')
              .attr('stroke-width', 1.5);
            d3.select(tooltipRef.current).style('z-index', 12);
            d3.select(tooltipRef.current).style('opacity', 0.9);
            
            // Create corporate-standard tooltip
            const nodeType = (d.labels && d.labels.length > 0) ? d.labels[0] : (d.label || 'Unknown');
            const props = d.properties || {};
            
            let tooltipContent = `
              <div style="background: linear-gradient(135deg, #0066B3 0%, #28A745 100%); color: white; padding: 8px 12px; margin: -8px -8px 8px -8px; font-weight: bold; border-radius: 4px 4px 0 0;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <i className="fas fa-chart-bar" style={{ fontSize: '16px', color: '#666' }}></i>
                  <span>${nodeType}</span>
                </div>
              </div>
            `;
            
            // Add primary identification
            // Primary identification: name + version (external_version preferred)
            const displayPrimary = getDisplayLabel(d);
            tooltipContent += `<div style="margin-bottom: 6px; font-size: 15px; font-weight: 600; color: #2C2C2C;">${displayPrimary}</div>`;
            
            // Add element ID
            // Removed elementId display per UX requirement
            
            // Add properties in organized sections
            const priorityProps = ['external_version', 'version', 'status', 'type', 'description'];
            const shownProps = new Set();
            
            // Show priority properties first
            priorityProps.forEach(prop => {
              if (props[prop]) {
                const icon = prop === 'external_version' ? '[EV]' : prop === 'version' ? '[V]' : prop === 'status' ? '[S]' : prop === 'type' ? '[T]' : '[P]';
                tooltipContent += `<div style="margin: 4px 0; display: flex; align-items: center; gap: 6px;"><span>${icon}</span><strong>${prop}:</strong> ${props[prop]}</div>`;
                shownProps.add(prop);
              }
            });
            
            // Show remaining properties
            const remainingProps = Object.entries(props).filter(([k]) => !shownProps.has(k) && !['name', 'title'].includes(k));
            if (remainingProps.length > 0) {
              tooltipContent += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #ecf0f1; font-size: 12px;">`;
              remainingProps.forEach(([k, v]) => {
                tooltipContent += `<div style="margin: 2px 0;"><strong>${k}:</strong> ${v}</div>`;
              });
              tooltipContent += `</div>`;
            }
            
            d3.select(tooltipRef.current).html(tooltipContent)
              .style('left', `${event.pageX + 10}px`)
              .style('top', `${event.pageY - 15}px`);
          })
          .on('mouseout', function () {
            d3.select(this).select('.main-icon')
              .attr('stroke', null)
              .attr('stroke-width', null);
            d3.select(this).select('.fallback-circle')
              .attr('stroke', null)
              .attr('stroke-width', null);
            d3.select(tooltipRef.current).style('opacity', 0);
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
 
    return () => {
      if (simulationRef.current) {
        simulationRef.current.stop();
        simulationRef.current = null; // Clear reference for memory cleanup
        console.log('D3 Simulation stopped and cleared on component unmount.');
      }
      // Clear any remaining event listeners
      if (gRef.current) {
        gRef.current.selectAll('*').on('.drag', null);
      }
    };
    
    // Performance monitoring
    const endTime = performance.now();
    const renderTime = endTime - startTime;
    console.log(`Render completed in ${renderTime.toFixed(2)}ms`);
    
    // Performance warnings
    if (renderTime > 1000) {
      console.warn(`Slow render detected: ${renderTime.toFixed(2)}ms with ${filteredData.nodes?.length || 0} nodes`);
    }
    if (renderTime > 2000) {
      console.error(`🚨 Very slow render: ${renderTime.toFixed(2)}ms - consider optimization`);
    }
 
  }, [filteredData, layoutType, treeExpandedNodes]);

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
  }, [graphData]);

  // Reset expanded nodes when search query changes
  useEffect(() => {
    setExpandedNodes(new Set());
    setNodeExpansions(new Map());
  }, [searchQuery]);
 
  return (
    <div
      className="graph-heb-root"
      style={{
        position: 'relative',
        width: '100%',
        height: '80vh',
        backgroundColor: '#fafbfc',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Tools dropdown replacing standalone Compare Nodes button */}
  <div style={{ position:'absolute', top:10, right:10, zIndex:2100 }}>
        <div className="dropdown" style={{ position:'relative' }}>
          <button
            className="btn btn-sm dropdown-toggle"
            type="button"
            onClick={(e)=>{
              const menu = e.currentTarget.nextSibling; if(menu) menu.classList.toggle('show');
            }}
            style={{
              backgroundColor:'#0a8276',
              color:'#fff',
              fontWeight:600,
              border:'1px solid #0a8276',
              padding:'8px 14px',
              boxShadow:'0 2px 6px rgba(0,0,0,0.15)'
            }}
          >🛠 Tools</button>
          <div
            className="dropdown-menu p-2"
            style={{
              minWidth:180,
              background:'#0a8276',
              color:'#fff',
              border:'1px solid #0a8276',
              boxShadow:'0 4px 12px rgba(0,0,0,0.25)',
              position:'absolute',
              top:'100%',
              right:0,
              left:'auto',
              marginTop:4
            }}
          >
            <button
              className="dropdown-item"
              style={{ color:'#fff', fontSize:13, fontWeight:500, cursor:'pointer' }}
              onClick={()=>{ if(typeof setActiveTab==='function'){ setActiveTab('whereused'); } }}
            >🔍 Where Used</button>
            <button
              className="dropdown-item"
              style={{ color:'#fff', fontSize:13, fontWeight:500, cursor:'pointer' }}
              onClick={()=>{ setShowComparativeSearch(true); }}
            >Compare Nodes</button>
          </div>
        </div>
      </div>
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
              fontSize: '14px',
              lineHeight: 1.2,
              background: '#fff'
            }}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') setSearchQuery(e.target.value); }}
            onFocus={e => { e.target.style.borderColor = '#0066B3'; e.target.style.boxShadow='0 0 0 2px rgba(0,102,179,0.15)'; }}
            onBlur={e => { e.target.style.borderColor = '#cfd6dc'; e.target.style.boxShadow='none'; }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <i className="fas fa-chart-bar" style={{ fontSize: '14px', color: '#555' }}></i>
          <select
            value={layoutType}
            onChange={(e) => handleLayoutChange(e.target.value)}
            disabled={isLayoutSwitching || searchLoading}
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid #4a90e2',
              backgroundColor: isLayoutSwitching ? '#ADB5BD' : '#6C757D',
              color: '#fff',
              cursor: isLayoutSwitching ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              fontWeight: 500,
              minWidth: '180px',
              transition: 'all .2s ease'
            }}
            title={isLayoutSwitching ? 'Layout switching in progress...' : 'Select graph layout type'}
          >
            <option value="force-directed" style={{color:'#333'}}>🌐 Force-Directed Graph</option>
            <option value="indented-tree" style={{color:'#333'}}>📋 Indented Tree Layout</option>
          </select>
        </div>
        {(searchLoading || isLayoutSwitching) && (
          <div style={{display:'flex', alignItems:'center', gap:6, fontSize:13, color:'#4a90e2'}}>
            <div className="spinner" style={{width:14,height:14,border:'2px solid #f3f3f3',borderTop:'2px solid #6C757D',borderRadius:'50%',animation:'spin 1s linear infinite'}}></div>
            {searchLoading ? 'Searching…' : 'Switching layout…'}
          </div>
        )}
        {searchQuery && (
          <button
            onClick={() => {
              setSearchQuery('');
              setSearchInput('');
              setExpandedNodes(new Set());
              setNodeExpansions(new Map());
              setData(initialData);
              setGraphData(initialData);
              setFilteredData(initialData);
              setFullDataset(initialData);
              if (setSearchResults) setSearchResults(initialData.nodes);
            }}
            style={{padding:'6px 12px', border:'none', borderRadius:'6px', background:'linear-gradient(135deg,#ff6b6b,#ee5a52)', color:'#fff', fontSize:13, fontWeight:600, cursor:'pointer', boxShadow:'0 2px 6px rgba(255,107,107,.35)'}}
          >🔄 Reset</button>
        )}
        <button
          onClick={toggleChat}
          style={{padding:'6px 12px', border:'none', borderRadius:'6px', background: showChat ? '#004D87' : '#28A745', color:'#fff', fontSize:13, fontWeight:600, cursor:'pointer'}}
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
          <div style={{ marginBottom: '16px', fontSize: '48px' }}>⏳</div>
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
 
  {/* Offset SVG slightly so internal graph/tree headers don't visually collide with the toolbar */}
  <svg ref={svgRef} style={{ width: '100%', height: '100%', flexGrow: 1, marginTop: '8px' }}></svg>
 
      <div ref={tooltipRef} className="tooltip" style={{
        position: 'absolute', 
        opacity: showComparativeSearch ? 0 : 0, 
        background: 'rgba(0,0,0,0.7)', 
        color: 'white',
        padding: '8px', 
        borderRadius: '4px', 
        pointerEvents: 'none', 
        maxWidth: '300px', 
        fontSize: '0.8em', 
        zIndex: showComparativeSearch ? -1 : 12,
        display: showComparativeSearch ? 'none' : 'block'
      }} />
      <div ref={relationTooltipRef} className="tooltip" style={{
        position: 'absolute', 
        opacity: showComparativeSearch ? 0 : 0, 
        background: 'rgba(0,0,0,0.7)', 
        color: 'white',
        padding: '8px', 
        borderRadius: '4px', 
        pointerEvents: 'none', 
        maxWidth: '300px', 
        fontSize: '0.8em', 
        zIndex: showComparativeSearch ? -1 : 12,
        display: showComparativeSearch ? 'none' : 'block'
      }} />
      
      {/* Comparative Search Modal */}
      {showComparativeSearch && (
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
                onClick={() => {
                  setShowComparativeSearch(false);
                  setCompareSearchResults({ left: null, right: null });
                  setComparisonData(null);
                  setCompareSearchInputs({
                    left: { nodeType: '', name: '', version: '' },
                    right: { nodeType: '', name: '', version: '' }
                  });
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '24px',
                  cursor: 'pointer',
                  color: '#ffffff'
                }}
              >
                ×
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
                      <button onClick={()=> setSelectedCompareNodeA(null)} style={{ background:'none', border:'none', color:'#0066B3', cursor:'pointer', fontSize:12 }}>✕</button>
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
                      <button onClick={()=> setSelectedCompareNodeB(null)} style={{ background:'none', border:'none', color:'#FF6600', cursor:'pointer', fontSize:12 }}>✕</button>
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
};

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
 
export default GraphHEB;

