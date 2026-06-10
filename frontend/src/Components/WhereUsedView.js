import React, { useCallback, useMemo, useState } from 'react';
import '../App.css';
import { API, buildUrl, replaceParams } from '../config';
import { apiClient } from '../services/apiClient';
import { useSchema } from '../SchemaContext';
import DataGridWidget from '../widgets/DataGridWidget';
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

const WU = {
    primary: '#004B87',
    primarySoft: '#E8F1FC',
    surface: '#FFFFFF',
    bg: '#F8F9FA',
    border: '#D9E2EC',
    borderStrong: '#BCCCDC',
    text: '#1A2B3C',
    muted: '#52606D',
    subtle: '#7B8794',
    error: '#C0392B',
};

const panelStyle = {
    background: WU.surface,
    border: `1px solid ${WU.border}`,
    borderRadius: 8,
    boxShadow: '0 4px 14px rgba(15, 23, 42, 0.06)',
    padding: 12,
    boxSizing: 'border-box',
};

const fieldLabelStyle = {
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: 0,
    color: WU.muted,
    textTransform: 'uppercase',
};

const inputStyle = {
    width: '100%',
    minHeight: 36,
    padding: '8px 11px',
    border: `1px solid ${WU.borderStrong}`,
    borderRadius: 6,
    fontSize: 13,
    color: WU.text,
    boxSizing: 'border-box',
    outline: 'none',
};

const buttonStyle = {
    minHeight: 36,
    padding: '8px 14px',
    border: 'none',
    borderRadius: 6,
    background: WU.primary,
    color: '#fff',
    fontSize: 13,
    fontWeight: 700,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
};

const WhereUsedView = ({
    data,
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
    // Schema-driven display
    const { getDisplayName: schemaDisplayName } = useSchema() || {};
    // Removed viewMode toggle; always show hierarchy view per latest requirements
    
    // Unified search using same backend logic as GraphHEB (POST /graphfilter)
    const handleSearch = async () => {
        const term = searchTerm.trim();
        if (!term) return;
        setIsSearching(true);
        setSearchError(null);
        try {
            // Use graphfilter endpoint similar to GraphHEB implementation
            const response = await apiClient.post(buildUrl(API.graph.graphfilter), { search: term.toLowerCase() });
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
    const expandAllParents = useCallback(async (startNode) => {
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
                    const resp = await apiClient.get(buildUrl(replaceParams(API.graph.graphtraverseNode, { node_id: currentNode.elementId })));
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
    }, []);

    // Select node and build tree
    const handleNodeSelect = useCallback((node) => {
        setSelectedNode(node);
        setTreeData(null);
        setLevels([]);
        setAutoExpanded(false);
        expandAllParents(node);
    }, [expandAllParents]);

    const getNodeDisplayName = useCallback((node) => {
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
    }, [schemaDisplayName]);

    const getNodeRelationships = useCallback((nodeId) => {
        if (!treeData?.links?.length || !nodeId) return [];
        return treeData.links.filter(link => link.source === nodeId || link.target === nodeId);
    }, [treeData]);

    const searchGridRows = useMemo(() => hierarchySearchResults.map((node) => {
        const nodeLabel = node.labels?.[0] || node.label || 'Node';
        return {
            id: node.elementId,
            displayName: getNodeDisplayName(node),
            label: nodeLabel,
            properties: Object.keys(node.properties || node).filter(k => !['elementId', 'labels', 'label'].includes(k)).length,
            node,
        };
    }), [hierarchySearchResults, getNodeDisplayName]);

    const hierarchyGridRows = useMemo(() => {
        if (!treeData || !levels.length) return [];
        return levels.flatMap((levelNodes, levelIndex) => {
            const depth = levels.length - 1 - levelIndex;
            return levelNodes.map((node) => {
                const relationships = getNodeRelationships(node.elementId);
                const nodeLabel = node.labels?.[0] || node.label || 'Node';
                return {
                    id: `${levelIndex}-${node.elementId}`,
                    depth,
                    level: depth === 0 ? 'Selected node' : `Ancestor level ${depth}`,
                    displayName: getNodeDisplayName(node),
                    label: nodeLabel,
                    relationships: relationships.map(link => link.type || 'RELATED').join(', ') || 'None',
                    relationshipCount: relationships.length,
                };
            });
        });
    }, [treeData, levels, getNodeDisplayName, getNodeRelationships]);

    const searchGridColumns = useMemo(() => [
        { headerName: 'Node', field: 'displayName', flex: 1.5, minWidth: 260, tooltipField: 'displayName' },
        { headerName: 'Label', field: 'label', flex: 0.7, minWidth: 160 },
        { headerName: 'Properties', field: 'properties', width: 120, type: 'numericColumn' },
        {
            headerName: 'Action',
            field: 'id',
            width: 150,
            pinned: 'right',
            sortable: false,
            filter: false,
            cellRenderer: (params) => (
                <button
                    type="button"
                    onClick={() => handleNodeSelect(params.data.node)}
                    style={{
                        ...buttonStyle,
                        minHeight: 28,
                        padding: '4px 10px',
                        fontSize: 12,
                        background: selectedNode?.elementId === params.data.id ? WU.subtle : WU.primary,
                    }}
                    title="Load where-used hierarchy for this node"
                >
                    Select
                </button>
            ),
        },
    ], [selectedNode, handleNodeSelect]);

    const hierarchyGridColumns = useMemo(() => [
        { headerName: 'Level', field: 'level', width: 170 },
        { headerName: 'Depth', field: 'depth', width: 95, type: 'numericColumn' },
        { headerName: 'Node', field: 'displayName', flex: 1.4, minWidth: 260, tooltipField: 'displayName' },
        { headerName: 'Label', field: 'label', flex: 0.6, minWidth: 150 },
        { headerName: 'Relationships', field: 'relationships', flex: 1, minWidth: 220, tooltipField: 'relationships' },
        { headerName: 'Links', field: 'relationshipCount', width: 90, type: 'numericColumn' },
    ], []);

    return (
        <div style={{ padding: '14px 18px', boxSizing: 'border-box', overflow: 'hidden', display:'flex', flexDirection:'column', flex:1, minHeight:0, background: WU.bg }}>
            <div style={{ ...panelStyle, marginBottom: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 1fr) auto', gap: 10, alignItems: 'end' }}>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
                        <span style={fieldLabelStyle}>Node search</span>
                        <input
                            type="text"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            placeholder="Enter part, class, instance, requirement, or property name"
                            style={inputStyle}
                            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                        />
                    </label>
                    <button
                        onClick={handleSearch}
                        disabled={isSearching || !searchTerm.trim()}
                        style={{
                            ...buttonStyle,
                            background: isSearching || !searchTerm.trim() ? WU.subtle : WU.primary,
                            cursor: isSearching || !searchTerm.trim() ? 'not-allowed' : 'pointer'
                        }}
                    >
                        {isSearching ? 'Searching...' : 'Search'}
                    </button>
                </div>
                {searchError && (
                    <div style={{ marginTop: 8, color: WU.error, fontSize: 12, fontWeight: 600 }}>{searchError}</div>
                )}
            </div>
            {/* Search Results */}
            {hierarchySearchResults.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                    <DataGridWidget
                        title={`Matching nodes (${hierarchySearchResults.length})`}
                        rows={searchGridRows}
                        columns={searchGridColumns}
                        height={220}
                        emptyLabel="No matching nodes"
                    />
                </div>
            )}

            {/* Where-used hierarchy */}
            {treeData && (
                <div style={{ flex:1, display:'flex', flexDirection:'column', minHeight:0 }}>
                    <div style={{ ...panelStyle, display:'flex', alignItems:'center', gap:12, flexWrap:'wrap', marginBottom:8, padding: '10px 12px' }}>
                        <div style={{ minWidth: 260, flex: '1 1 320px' }}>
                            <div style={fieldLabelStyle}>Parent hierarchy</div>
                            <div style={{ fontSize: 14, color: WU.text, fontWeight: 800, marginTop: 4 }}>{getNodeDisplayName(selectedNode)}</div>
                        </div>
                        <span style={{ fontSize: 12, color: WU.muted, fontWeight: 700 }}>Levels {levels.length}</span>
                        <span style={{ fontSize: 12, color: WU.muted, fontWeight: 700 }}>Ancestors {treeData.nodes.length - 1}</span>
                        <span style={{ fontSize: 12, color: WU.muted, fontWeight: 700 }}>Links {treeData.links.length}</span>
                        {isExpandingUpwards && <span style={{ color: WU.primary, fontSize: 12, fontWeight: 700 }}>Expanding...</span>}
                        {expansionError && <span style={{ color: WU.error, fontSize: 12, fontWeight: 700 }}>Error: {expansionError}</span>}
                        {!autoExpanded && !isExpandingUpwards && (
                            <button onClick={() => expandAllParents(selectedNode)} style={buttonStyle}>Expand Upwards</button>
                        )}
                    </div>
                    <div style={{ flex: 1, minHeight: 0 }}>
                        <DataGridWidget
                            title="Where-used hierarchy"
                            rows={hierarchyGridRows}
                            columns={hierarchyGridColumns}
                            height={420}
                            emptyLabel="No hierarchy rows"
                        />
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
