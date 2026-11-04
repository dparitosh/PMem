import React from 'react';
import {render,screen} from '@testing-library/react';
import {vi} from 'vitest';
import SysMLDiagram from './SysMLDiagram';
let edges;
vi.mock('@xyflow/react',()=>({
 ReactFlow:({nodes,edges:items,nodeTypes,children})=>{edges=items;const Node=nodeTypes.sysml;return <div>{nodes.map(node=><Node key={node.id} data={node.data}/>)}{children}</div>},
 Background:()=>null,Controls:()=>null,Handle:()=>null,Position:{Left:'left',Right:'right'},applyNodeChanges:(_,nodes)=>nodes
}));
test('requirement view uses SysML stereotype and source text with dashed derive relation',()=>{
 render(<SysMLDiagram graph={{nodes:[{id:'r',label:'Drive torque',type:'Requirement',properties:{profile_Text:'Torque shall exceed 10 Nm'}}],links:[{id:'derive',source:'r',target:'r',type:'DERIVE_REQT'}]}} diagram={{id:'view',name:'Drive requirements',type:'Requirement Diagram'}} onSelect={()=>{}}/>);
 expect(screen.getByText('«requirement»')).toBeInTheDocument();
 expect(screen.getByText(/Torque shall exceed/)).toBeInTheDocument();
 expect(edges[0].label).toBe('«deriveReqt»');expect(edges[0].style.strokeDasharray).toBe('6 4');
});
test('use cases have ellipse notation and missing source drawing content is explicit',()=>{
 const view=render(<SysMLDiagram graph={{nodes:[{id:'u',label:'Produce sugar',type:'uml:UseCase',properties:{}}],links:[]}} diagram={{id:'view',name:'Production',type:'SysML Use Case Diagram'}}/>);
 expect(screen.getByText('Produce sugar').closest('.sysml-node')).toHaveClass('sysml-usecase');
 view.rerender(<SysMLDiagram graph={{nodes:[],links:[]}} diagram={{id:'empty',name:'Missing view',type:'Requirement Diagram'}}/>);
 expect(screen.getByText(/No drawable members were exported/)).toBeInTheDocument();
});


test('filtered emptiness is distinct from missing source and internal ids do not displace business text',()=>{
 const view=render(<SysMLDiagram graph={{nodes:[],links:[]}} filtered diagram={{id:'v',name:'View',type:'Requirement Diagram'}}/>);
 expect(screen.getByText(/No elements match the current filter/)).toBeInTheDocument();
 view.rerender(<SysMLDiagram graph={{nodes:[{id:'r',label:'Safety',type:'SafetyRequirement',properties:{id:'technical-secret-id',profile_id:'internal-profile',profile_applications:[{stereotype:'SafetyRequirement',Id:'REQ-7',Text:'Drive shall stop safely'}]}}],links:[]}} diagram={{id:'v',name:'View',type:'Requirement Diagram'}}/>);
 expect(screen.getByText('«SafetyRequirement»')).toBeInTheDocument();
 expect(screen.getByText(/Drive shall stop safely/)).toBeInTheDocument();
 expect(screen.queryByText(/technical-secret-id/)).toBeNull();
});
