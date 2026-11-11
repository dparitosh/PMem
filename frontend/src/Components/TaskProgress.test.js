import React from 'react';
import {render,screen} from '@testing-library/react';
import TaskProgress from './TaskProgress';
test('a completed execution with a review hold does not claim publication',()=>{
 render(<TaskProgress kind="workflow" run={{run_id:'test',status:'completed',traces:[{status:'completed',result:{status:'held',summary:'Mapping needs review'}}]}}/>);
 expect(screen.getByRole('status')).toHaveTextContent('Review required');
 expect(screen.getByText(/No publication is established/)).toBeVisible();
});
test('uncertain writes require verification and expose selected evidence without raw payloads',()=>{
 render(<TaskProgress kind="workflow" run={{run_id:'test',status:'reconciliation_required',page_context:{page:'ontology',ontology_id:'selected'},traces:[{status:'completed',result:{iri:'urn:Part',prompt:'private prompt',execution_payload:'private execution'}}]}}/>);
 expect(screen.getByRole('status')).toHaveTextContent('Outcome needs verification');
 expect(screen.queryByText('selected')).not.toBeInTheDocument();
 expect(screen.queryByText('Source identities and scope')).not.toBeInTheDocument();
 expect(screen.queryByText('urn:Part')).not.toBeInTheDocument();
 expect(screen.queryByText(/private prompt|private execution/)).not.toBeInTheDocument();
});

test('recommendation results prefer recorded business findings over a repeated model plan',()=>{
 render(<TaskProgress run={{status:'completed',result:{summary:'Plan to investigate later',business_summary:'Housing — assembly records: 1. Review required.'}}}/>);
 expect(screen.getByText('Housing — assembly records: 1. Review required.')).toBeVisible();
 expect(screen.queryByText('Plan to investigate later')).not.toBeInTheDocument();
});


test('vendor names do not leak through retained task prose',()=>{
 render(<TaskProgress run={{status:'completed',goal:'Semantica review',message:'Neo4j is available',plans:[{subtasks:['Check Semantica policy']}],result:{summary:'Semantica passed; Neo4j retained the result'}}}/>);
 expect(document.body.textContent).not.toMatch(/semantica|neo4j/i);
 expect(screen.queryByText(/Current plan|Recorded actions|knowledge graph is available/)).not.toBeInTheDocument();
});

 test('business findings omit background plans, tool names and execution errors',()=>{
 render(<TaskProgress run={{status:'completed',plans:[{subtasks:['Call internal tool']}],observations:[{tool_id:'internal.sql'}],error_type:'RuntimeError',result:{business_summary:'Housing has one recorded requirement.'}}}/>);
 expect(screen.getByText('Housing has one recorded requirement.')).toBeVisible();
 expect(document.body.textContent).not.toMatch(/internal.sql|Call internal tool|RuntimeError|Recorded actions/);
 });
