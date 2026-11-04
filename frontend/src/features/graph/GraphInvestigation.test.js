import React from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { vi } from 'vitest';
import GraphInvestigation from './GraphInvestigation';
let props;
vi.mock('../../Components/ReadGoalPanel',()=>({default: value => {props=value;return <button disabled={value.disabled}>{value.startLabel}</button>;}}));
afterEach(()=>{cleanup();props=null;});
test('no selected node cannot start an investigation',()=>{
 render(<GraphInvestigation nodeCount={30} relationshipCount={40}/>);
 expect(screen.getByText(/Click a graph node/)).toBeInTheDocument();
 expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
test('investigation retains exact identity, bounded scope and read-only evidence requirements',()=>{
 render(<GraphInvestigation node={{elementId:'neo:42',properties:{name:'Bearing issue',part_type:'ChangeRequestRevision'}}} ontologyId="ontology-version-2" nodeCount={3} relationshipCount={4}/>);
 expect(props.agent).toBe('graph-analyst');
 expect(props.context).toMatchObject({node_id:'neo:42',ontology_id:'ontology-version-2',page:'graph'});
 expect(props.task).toContain('bounded slice (3 nodes, 4 relationships)');
 expect(props.task).toContain('Do not publish or alter data');
 fireEvent.change(screen.getByLabelText('Business question'),{target:{value:'Which requirements have a direct trace link?'}});
 expect(props.task).toContain('Which requirements have a direct trace link?');
 fireEvent.change(screen.getByLabelText('Business question'),{target:{value:' '}});
 expect(props.disabled).toBe(true);
});
test('ALL scope is not sent as an ontology identity',()=>{
 render(<GraphInvestigation node={{elementId:'record',name:'Part'}} ontologyId="ALL" nodeCount={1} relationshipCount={0}/>);
 expect(props.context.ontology_id).toBeUndefined();
});

test('model investigations retain model page and distinguish schema from business instances',()=>{
 render(<GraphInvestigation node={{elementId:'model:42',properties:{name:'Drive requirements'}}} ontologyId="sysml-v2" nodeCount={4} relationshipCount={3} page="modeling"/>);
 expect(props.context).toMatchObject({page:'modeling',node_id:'model:42',ontology_id:'sysml-v2'});
 expect(props.task).toContain('not necessarily a manufactured business instance');
 fireEvent.change(screen.getByLabelText('Engineering task'),{target:{value:'Trace recorded requirement, function and component relationships for this element. Cite each path and identify missing traceability; do not claim satisfaction without evidence.'}});
 expect(props.task).toContain('do not claim satisfaction without evidence');
 expect(props.task).toContain('Do not publish or alter data');
});
