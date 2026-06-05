import React from 'react'
import '../App.css';
import { SimpleTreeView } from '@mui/x-tree-view/SimpleTreeView';

import { TreeItem } from '@mui/x-tree-view/TreeItem';

const TableView = (props) => {
    const data = props.data;
    // Function to get display name for nodes (same logic as graph view)
    const getNodeDisplayName = (node) => {
        if (node?.label === 'MILESTONE') {
            return node?.milestone_abbreviation || node?.label;
        } else if (node?.label === 'WORKPRODUCT') {
            return node?.name || node?.label;
        } else if (Object.keys(node || {}).some(key => key.startsWith('project_'))) {
            return node?.name || node?.label;
        } else if (node?.label === 'KlusaProject') {
            return node?.name || node?.label;
        } else if (node?.label === 'JiraProject') {
            return node?.jira_project_key || node?.label;
        } else if (node?.label === 'Chip' || node?.label === 'Design Block' || node?.label === 'Software' || node?.label === 'SPS Legacy' || node?.label === 'Document') {
            const name = node?.name || node?.label;
            if (node?.label === 'SPS Legacy' || node?.label === 'Software' || node?.label === 'Design Block' || node?.label === 'Chip') {
                const version = node?.external_version || node?.version;
                if (version) {
                    return `${name}, ${version}`;
                }
            }
            return name;
        } else {
            return node?.label || 'Unknown';
        }
    };

    const treeViewData = (data, label) => {
        return (
            <SimpleTreeView>
              <TreeItem itemId="grid" label={label?.toLowerCase()}>
                {Object.entries(data).map((keys) => {
                    const key = keys?.[0] ?? '';
                    const val = keys?.[1] ?? '';
                    return <TreeItem itemId={keys} label={key + ':' + val} /> 
                }
                )
                }
              </TreeItem>
            </SimpleTreeView>
        );
    }
    function renderTableData() {
        return data?.links?.map((links) => {
            const { elementId, source, target, type } = links //destructuring
            const sourceNode = data?.nodes.filter(data => data.elementId === source);
            const targetNode = data?.nodes.filter(data => data.elementId === target); 
            
            // Get display names using the same logic as graph view
            const sourceDisplayName = getNodeDisplayName(sourceNode[0]);
            const targetDisplayName = getNodeDisplayName(targetNode[0]);
            
            return (
                <tr key={elementId}> 
                 <td>{treeViewData(sourceNode[0], sourceDisplayName)}</td>
                 <td title={type} style={{paddingTop:'20px'}}>{type.toLowerCase().replace('has_', '')}</td>
                 <td>{treeViewData(targetNode[0], targetDisplayName)}</td>
              </tr>
           )
         })
    }

    return (
        <div style={{ marginLeft: '20px', border: '1px solid #ddd', marginTop: '45px', marginRight:'10px', borderRadius: 6, maxWidth: '100%',overflow: 'auto', height: '90%'}}>
            <table className='table table-striped'>
                <thead className='sticky-top'>
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
