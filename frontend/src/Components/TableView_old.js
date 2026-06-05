import React from 'react'
import '../App.css';
import { SimpleTreeView } from '@mui/x-tree-view/SimpleTreeView';

import { TreeItem } from '@mui/x-tree-view/TreeItem';

const TableView = (props) => {
    const data = props.data;
    const searchResults = props.searchResults;
    const chatResults = props.chatResults;
    const visibleRelationships = props.visibleRelationships;
    
    // Determine what to show based on current state
    const getVisibleData = () => {
        // If there are search results, show their relationships
        if (searchResults && searchResults.length > 0) {
            const searchNodeIds = new Set(searchResults.map(node => node.elementId));
            
            // Find all relationships that involve any search result node
            const searchRelationships = data?.links?.filter(link => 
                searchNodeIds.has(link.source) || searchNodeIds.has(link.target)
            ) || [];
            
            // Always show relationships if they exist for search results
            if (searchRelationships.length > 0) {
                return {
                    showNodesOnly: false,
                    visibleNodes: searchResults,
                    visibleRelationships: searchRelationships
                };
            }
            
            // No relationships found, show just the nodes
            return {
                showNodesOnly: true,
                visibleNodes: searchResults,
                visibleRelationships: []
            };
        }
        
        // If there are chat results, apply similar logic
        if (chatResults && chatResults.length > 0) {
            const chatNodeIds = new Set(chatResults.map(node => node.elementId));
            
            const chatRelationships = data?.links?.filter(link => 
                chatNodeIds.has(link.source) || chatNodeIds.has(link.target)
            ) || [];
            
            if (chatRelationships.length > 0) {
                return {
                    showNodesOnly: false,
                    visibleNodes: chatResults,
                    visibleRelationships: chatRelationships
                };
            }
            
            return {
                showNodesOnly: true,
                visibleNodes: chatResults,
                visibleRelationships: []
            };
        }
        
        // Default: show all data (when no search/chat filters)
        return {
            showNodesOnly: false,
            visibleNodes: data?.nodes || [],
            visibleRelationships: data?.links || []
        };
    };
    
    const { showNodesOnly, visibleNodes, visibleRelationships: tableRelationships } = getVisibleData();

    // Build a fast lookup map for nodes by elementId (avoid repeated filtering)
    const nodeMap = React.useMemo(() => {
        const map = new Map();
        (data?.nodes || []).forEach(n => {
            if (n?.elementId) map.set(n.elementId, n);
        });
        return map;
    }, [data]);
    // Function to get display name for nodes - generic version
    const getNodeDisplayName = (node) => {
        const nodeLabel = node?.labels?.[0] || node?.label;
        
        // Try various generic property names in order of preference
        const name = node?.name || 
                     node?.title || 
                     node?.code || 
                     node?.key || 
                     node?.abbreviation || 
                     node?.milestone_abbreviation ||
                     node?.jira_project_key ||
                     nodeLabel;
        
        // If there's a version, append it
        const version = node?.external_version || node?.version;
        if (version) {
            return `${name}, ${version}`;
        }
        
        return name || 'Unknown';
    };

    const treeViewData = (nodeData, label) => {
        const entries = Object.entries(nodeData || {});
        return (
            <SimpleTreeView>
                <TreeItem itemId={`root-${nodeData?.elementId || label}`} label={label?.toLowerCase()}>
                    {entries.map(([k, v]) => {
                        // Force string itemId and unique key
                        const childId = `child-${nodeData?.elementId || label}-${k}`;
                        return (
                            <TreeItem
                                key={childId}
                                itemId={childId}
                                label={`${k}:${v}`}
                            />
                        );
                    })}
                </TreeItem>
            </SimpleTreeView>
        );
    };
    function renderTableData() {
        // If showing nodes only (no relationships expanded)
        if (showNodesOnly) {
            return visibleNodes.map((node) => {
                const displayName = getNodeDisplayName(node);
                return (
                    <tr key={node.elementId}> 
                     <td>{treeViewData(node, displayName)}</td>
                     <td style={{paddingTop:'20px', color: '#888'}}>-</td>
                     <td style={{paddingTop:'20px', color: '#888'}}>-</td>
                  </tr>
               );
            });
        }
        
        // Show relationships
        return tableRelationships.map((link) => {
            // Handle cases where source/target might be objects or IDs
            const rawSource = link.source?.elementId || link.source; 
            const rawTarget = link.target?.elementId || link.target;
            const sourceNode = nodeMap.get(rawSource);
            const targetNode = nodeMap.get(rawTarget);
            const relationType = (link.type || '').toLowerCase().replace(/^has_/, '');

            const sourceDisplayName = getNodeDisplayName(sourceNode) || rawSource || 'Unknown';
            const targetDisplayName = getNodeDisplayName(targetNode) || rawTarget || 'Unknown';

            return (
                <tr key={link.elementId || `${rawSource}-${relationType}-${rawTarget}`}> 
                    <td>{sourceNode ? treeViewData(sourceNode, sourceDisplayName) : <span style={{color:'#a00'}}>{sourceDisplayName}</span>}</td>
                    <td title={link.type} style={{paddingTop:'20px'}}>{relationType || 'relation'}</td>
                    <td>{targetNode ? treeViewData(targetNode, targetDisplayName) : <span style={{color:'#a00'}}>{targetDisplayName}</span>}</td>
                </tr>
            );
        });
    }

    return (
        <div style={{ 
            margin: '20px', 
            border: '1px solid #ddd', 
            borderRadius: 6, 
            height: 'calc(100vh - 180px)', 
            overflow: 'auto',
            backgroundColor: 'white'
        }}>
            <table className='table table-striped' style={{ marginBottom: 0 }}>
                <thead className='sticky-top' style={{ backgroundColor: 'white', zIndex: 10 }}>
                    <tr>
                    <th>parent</th>
                    <th>relation type</th>
                    <th>child</th>
                    </tr>     
                </thead>
              <tbody>
                 {renderTableData()}
              </tbody>
           </table>
        </div>
     )
}

export default TableView

