import React, { useCallback, useEffect, useMemo, useState } from 'react';
import '../App.css';
import { API, buildUrl, replaceParams } from '../config';
import { apiClient } from '../services/apiClient';
import { useSchema } from '../SchemaContext';
import DataGridWidget from '../widgets/DataGridWidget';
import logger from '../utils/logger';
import { normalizeGraphDataset as normalizeGraphDatasetShared } from '../utils/graphUtils';

// ──── DEVELOPER CONFIG: Node Display Label ────────────────────────────────
//
// DISPLAY_NAME_PROPERTY  — priority-ordered list of node properties to try.
//   The first property found on a node is used as the display name.
//   Set to [] (empty array) to rely solely on the Neo4j label.
const DISPLAY_NAME_PROPERTY = ['name', 'title', 'code', 'key', 'abbreviation', 'id'];
//
// DISPLAY_MODE  — controls what is shown in the node label.
//   'both-label-first'  → "Label - PropertyValue"   (default)
//   'both-prop-first'   → "PropertyValue (Label)"
//   'label-only'        → "Label"
//   'property-only'     → "PropertyValue"
const DISPLAY_MODE = 'both-label-first';
// ───────────────────────────────────────────────────────────────────────────

const SEARCHABLE_NODE_KEYS = [
  'name', 'title', 'code', 'key', 'abbreviation', 'id', 'description', 'label',
  'external_id', 'external_version', 'version', 'entity_type', 'node_type',
  'source_name', 'target_name', 'class_name', 'type', 'value', 'identifier',
  'ontology_prefix', 'prefix', 'ontology_name', 'source_ontology', 'namespace',
  'import_id', 'file_name', 'filename', 'part_number', 'part_id', 'requirement_id',
];

const normalizeSearchValue = (value) => String(value || '').trim().toLowerCase();

const getNodeProps = (node) => node?.properties || node || {};

const getNodeLabel = (node) => node?.labels?.[0] || node?.label || 'Node';

const collectSearchableNodeValues = (node) => {
  const props = getNodeProps(node);
  const values = new Set([node?.elementId, getNodeLabel(node)]);

  SEARCHABLE_NODE_KEYS.forEach((key) => {
    if (props[key] != null) values.add(props[key]);
  });

  Object.entries(props).forEach(([key, value]) => {
    if (value == null) return;
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      values.add(value);
      values.add(key);
    }
  });

  return Array.from(values).map(normalizeSearchValue).filter(Boolean);
};

const scoreNodeMatch = (node, rawTerm) => {
  const term = normalizeSearchValue(rawTerm);
  if (!term) return 0;

  const props = getNodeProps(node);
  const label = normalizeSearchValue(getNodeLabel(node));
  const elementId = normalizeSearchValue(node?.elementId);
  const preferredName = normalizeSearchValue(resolveDisplayProp(props) || props.name || props.title || props.code || '');
  const corpus = collectSearchableNodeValues(node);

  let score = 0;
  if (elementId === term) score += 500;
  if (preferredName === term) score += 450;
  if (label === term) score += 350;
  if (preferredName.startsWith(term)) score += 220;
  if (elementId.startsWith(term)) score += 200;
  if (label.startsWith(term)) score += 150;
  if (corpus.some((value) => value.includes(term))) score += 80;
  if (corpus.some((value) => term.includes('*') && value.includes(term.replace(/\*/g, '')))) score += 60;
  return score;
};

const buildRelationshipKey = (relationship) => relationship?.elementId || `${relationship?.start || relationship?.source}-${relationship?.type}-${relationship?.end || relationship?.target}`;

const hydrateGraphNode = (rawNode) => {
  if (!rawNode) return null;
  return {
    ...rawNode.properties,
    elementId: rawNode.elementId,
    labels: rawNode.labels || ['Node'],
    label: rawNode.labels?.[0] || rawNode.label || 'Node',
  };
};

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
    const [fallbackGraphData, setFallbackGraphData] = useState({ nodes: [], links: [] });
    const [graphLoading, setGraphLoading] = useState(false);
    const [graphError, setGraphError] = useState('');
    // Schema-driven display
    const { getDisplayName: schemaDisplayName } = useSchema() || {};

    const effectiveGraphData = useMemo(() => {
        const hasPrimaryGraph = (data?.nodes || []).length > 0 || (data?.links || []).length > 0;
        return hasPrimaryGraph ? data : fallbackGraphData;
    }, [data, fallbackGraphData]);

    useEffect(() => {
        const hasPrimaryGraph = (data?.nodes || []).length > 0 || (data?.links || []).length > 0;
        if (hasPrimaryGraph || (fallbackGraphData.nodes || []).length > 0) return undefined;

        let cancelled = false;
        const loadGraph = async () => {
            setGraphLoading(true);
            setGraphError('');
            try {
                const response = await apiClient.get(buildUrl(API.graph.graphView), { params: { limit: 5000 } });
                const normalized = normalizeGraphDatasetShared(response.data);
                if (!cancelled) setFallbackGraphData(normalized);
            } catch (error) {
                if (!cancelled) setGraphError(error?.response?.data?.detail || error.message || 'Failed to load graph data for Where Used.');
            } finally {
                if (!cancelled) setGraphLoading(false);
            }
        };

        loadGraph();
        return () => { cancelled = true; };
    }, [data, fallbackGraphData.nodes]);
    
    // Unified search using same backend logic as GraphHEB (POST /graphfilter)
    const handleSearch = async () => {
        const term = searchTerm.trim();
        if (!term) return;
        setIsSearching(true);
        setSearchError(null);
        try {
            const response = await apiClient.post(buildUrl(API.graph.graphfilter), { search: term.toLowerCase() });
            const records = response.data?.results || [];
            const nodesMap = new Map();

            records.forEach(record => {
                [record['n'], record['m']].forEach((rawNode) => {
                    const hydrated = hydrateGraphNode(rawNode);
                    if (!hydrated?.elementId) return;
                    const existing = nodesMap.get(hydrated.elementId);
                    nodesMap.set(hydrated.elementId, existing ? { ...existing, ...hydrated } : hydrated);
                });
            });

            const nodes = Array.from(nodesMap.values())
                .map((node) => ({ node, score: scoreNodeMatch(node, term) }))
                .filter(({ score }) => score > 0)
                .sort((a, b) => b.score - a.score)
                .map(({ node }) => node);

            const localFallbackNodes = (effectiveGraphData?.nodes || [])
                .map((node) => ({ node, score: scoreNodeMatch(node, term) }))
                .filter(({ score }) => score > 0)
                .sort((a, b) => b.score - a.score)
                .map(({ node }) => node);

            const finalNodes = nodes.length > 0 ? nodes : localFallbackNodes;
            if (nodes.length === 0 && localFallbackNodes.length > 0) {
                setSearchError('Server search returned no ranked matches. Showing local graph matches.');
            }

            setHierarchySearchResults(finalNodes);
            if (finalNodes.length > 0) {
                handleNodeSelect(finalNodes[0]);
            } else {
                setSelectedNode(null);
                setTreeData(null);
                setLevels([]);
            }
        } catch (err) {
            logger.search('Search error (server):', err);
            try {
                const fallbackNodes = (effectiveGraphData?.nodes || [])
                    .map((node) => ({ node, score: scoreNodeMatch(node, term) }))
                    .filter(({ score }) => score > 0)
                    .sort((a, b) => b.score - a.score)
                    .map(({ node }) => node);
                setHierarchySearchResults(fallbackNodes);
                setSearchError('Server search failed. Showing local filtered results.');
                if (fallbackNodes.length > 0) {
                    handleNodeSelect(fallbackNodes[0]);
                } else {
                    setSelectedNode(null);
                    setTreeData(null);
                    setLevels([]);
                }
            } catch (_fe) {
                setHierarchySearchResults([]);
                setSearchError('Search failed.');
            }
        } finally {
            setIsSearching(false);
        }
    };

    // Upward expansion logic: recursively fetch parents via graphtraverse until top-level
    const expandAllParents = useCallback(async (startNode) => {
        if (!startNode?.elementId) return;
        setIsExpandingUpwards(true);
        setExpansionError(null);
        try {
            const ancestorMap = new Map([[startNode.elementId, startNode]]);
            const linkSet = new Map();
            const visited = new Set();
            const queue = [startNode.elementId];

            while (queue.length > 0) {
                const currentNodeId = queue.shift();
                if (!currentNodeId || visited.has(currentNodeId)) continue;
                visited.add(currentNodeId);

                try {
                    const resp = await apiClient.get(buildUrl(replaceParams(API.graph.graphtraverseNode, { node_id: currentNodeId })));
                    const records = resp.data?.results || [];

                    records.forEach((record) => {
                        const relationship = record['r'];
                        if (!relationship) return;

                        const relatedNodes = [record['n'], record['m']]
                            .map(hydrateGraphNode)
                            .filter(Boolean);
                        relatedNodes.forEach((node) => {
                            if (!ancestorMap.has(node.elementId)) {
                                ancestorMap.set(node.elementId, node);
                            }
                        });

                        const sourceId = relationship.start || relationship.source;
                        const targetId = relationship.end || relationship.target;
                        if (!sourceId || !targetId) return;

                        if (targetId === currentNodeId) {
                            const key = buildRelationshipKey(relationship);
                            if (!linkSet.has(key)) {
                                linkSet.set(key, {
                                    elementId: relationship.elementId || key,
                                    source: sourceId,
                                    target: targetId,
                                    type: relationship.type,
                                    properties: relationship.properties || {},
                                });
                            }
                            if (!visited.has(sourceId)) {
                                queue.push(sourceId);
                            }
                        }
                    });
                } catch (e) {
                    logger.warn('Traverse fetch failed for %s: %s', currentNodeId, e.message);
                }
            }

            const parentLinks = Array.from(linkSet.values());
            const distances = new Map([[startNode.elementId, 0]]);
            const pending = [startNode.elementId];

            while (pending.length) {
                const childId = pending.shift();
                const childDist = distances.get(childId) || 0;
                parentLinks.forEach((link) => {
                    if (link.target !== childId) return;
                    const parentId = link.source;
                    if (!distances.has(parentId) || distances.get(parentId) > childDist + 1) {
                        distances.set(parentId, childDist + 1);
                        pending.push(parentId);
                    }
                });
            }

            const levelMap = new Map();
            distances.forEach((dist, nodeId) => {
                const nodeObj = ancestorMap.get(nodeId);
                if (!nodeObj) return;
                if (!levelMap.has(dist)) levelMap.set(dist, []);
                levelMap.get(dist).push(nodeObj);
            });

            const sortedLevels = Array.from(levelMap.entries())
                .sort((a, b) => b[0] - a[0])
                .map((entry) => entry[1]);

            logger.data('WhereUsed - Hierarchy built:');
            logger.data('  Total nodes: %d', Array.from(ancestorMap.values()).length);
            logger.data('  Total links: %d', parentLinks.length);
            logger.data('  Levels: %d', sortedLevels.length);

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
                    nodeId: node.elementId,
                    node,
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
                    title="Show where this business object is used"
                >
                    Select
                </button>
            ),
        },
    ], [selectedNode, handleNodeSelect]);

    const usageSummary = useMemo(() => {
        if (!selectedNode || !treeData?.nodes?.length) return '';

        const selectedId = selectedNode.elementId;
        const directParents = (treeData.links || [])
            .filter((link) => link?.target === selectedId)
            .map((link) => treeData.nodes.find((node) => node.elementId === link.source))
            .filter(Boolean);

        const uniqueParents = Array.from(
            new Map(
                directParents.map((node) => [node.elementId, getNodeDisplayName(node)])
            ).values()
        );

        const selectedName = getNodeDisplayName(selectedNode);
        if (!uniqueParents.length) {
            return `${selectedName} is not currently shown as used by another loaded business object.`;
        }

        const preview = uniqueParents.slice(0, 3).join(', ');
        const suffix = uniqueParents.length > 3 ? ` and ${uniqueParents.length - 3} more` : '';
        return `${selectedName} is used in ${preview}${suffix}.`;
    }, [selectedNode, treeData, getNodeDisplayName]);

    const hierarchyGridColumns = useMemo(() => [
        { headerName: 'Level', field: 'level', width: 170 },
        { headerName: 'Depth', field: 'depth', width: 95, type: 'numericColumn' },
        { headerName: 'Node', field: 'displayName', flex: 1.4, minWidth: 260, tooltipField: 'displayName' },
        { headerName: 'Label', field: 'label', flex: 0.6, minWidth: 150 },
        { headerName: 'Relationships', field: 'relationships', flex: 1, minWidth: 220, tooltipField: 'relationships' },
        { headerName: 'Links', field: 'relationshipCount', width: 90, type: 'numericColumn' },
        {
            headerName: 'Action',
            field: 'nodeId',
            width: 140,
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
                        background: selectedNode?.elementId === params.data.nodeId ? WU.subtle : WU.primary,
                    }}
                    title="Focus on this business object"
                >
                    Focus
                </button>
            ),
        },
    ], [handleNodeSelect, selectedNode]);

    const totalSearchableNodes = (effectiveGraphData?.nodes || []).length;

    return (
        <div style={{ padding: '14px 18px', boxSizing: 'border-box', overflow: 'hidden', display:'flex', flexDirection:'column', flex:1, minHeight:0, background: WU.bg }}>
            <div style={{ ...panelStyle, marginBottom: 12, padding: '10px 12px' }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: WU.text, marginBottom: 4 }}>Business object where-used analysis</div>
                <div style={{ fontSize: 12, color: WU.muted, lineHeight: 1.5 }}>Search for a part, requirement, instance, or named business object. We rank matches, select the best one, then build its upward usage chain from the graph.</div>
                <div style={{ marginTop: 8, fontSize: 11, color: graphError ? WU.error : WU.subtle, fontWeight: 600 }}>
                    {graphLoading ? 'Loading graph context...' : graphError ? graphError : `${totalSearchableNodes} business-object candidates are available for local fallback search.`}
                </div>
            </div>
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
                        onRowClicked={(row) => row?.node && handleNodeSelect(row.node)}
                    />
                </div>
            )}

            {/* Where-used hierarchy */}
            {treeData && (
                <div style={{ flex:1, display:'flex', flexDirection:'column', minHeight:0 }}>
                    <div style={{ ...panelStyle, display:'flex', alignItems:'center', gap:12, flexWrap:'wrap', marginBottom:8, padding: '10px 12px' }}>
                        <div style={{ minWidth: 260, flex: '1 1 320px' }}>
                            <div style={fieldLabelStyle}>Business object</div>
                            <div style={{ fontSize: 14, color: WU.text, fontWeight: 800, marginTop: 4 }}>{getNodeDisplayName(selectedNode)}</div>
                        </div>
                        <span style={{ fontSize: 12, color: WU.muted, fontWeight: 700 }}>Usage levels {levels.length}</span>
                        <span style={{ fontSize: 12, color: WU.muted, fontWeight: 700 }}>Ancestors {treeData.nodes.length - 1}</span>
                        <span style={{ fontSize: 12, color: WU.muted, fontWeight: 700 }}>Links {treeData.links.length}</span>
                        {isExpandingUpwards && <span style={{ color: WU.primary, fontSize: 12, fontWeight: 700 }}>Expanding...</span>}
                        {expansionError && <span style={{ color: WU.error, fontSize: 12, fontWeight: 700 }}>Error: {expansionError}</span>}
                        {!autoExpanded && !isExpandingUpwards && (
                            <button onClick={() => expandAllParents(selectedNode)} style={buttonStyle}>Expand Upwards</button>
                        )}
                    </div>
                    <div style={{ ...panelStyle, marginBottom: 8, padding: '10px 12px', fontSize: 13, fontWeight: 600, color: WU.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {usageSummary || 'Select a business object to see where it is used.'}
                    </div>
                    <div style={{ flex: 1, minHeight: 0 }}>
                        <DataGridWidget
                            title="Business object usage"
                            rows={hierarchyGridRows}
                            columns={hierarchyGridColumns}
                            height={420}
                            emptyLabel="No business usage rows"
                            onRowClicked={(row) => row?.node && handleNodeSelect(row.node)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};

export default WhereUsedView;
