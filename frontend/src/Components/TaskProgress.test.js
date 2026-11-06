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
 expect(screen.getByText('selected')).toBeInTheDocument();
 expect(screen.getByText('Source identities and scope').closest('details')).not.toHaveAttribute('open');
 expect(screen.getByText('urn:Part')).toBeInTheDocument();
 expect(screen.queryByText(/private prompt|private execution/)).not.toBeInTheDocument();
});

test('recommendation results prefer recorded business findings over a repeated model plan',()=>{
 render(<TaskProgress run={{status:'completed',result:{summary:'Plan to investigate later',business_summary:'Housing — assembly records: 1. Review required.'}}}/>);
 expect(screen.getByText('Housing — assembly records: 1. Review required.')).toBeVisible();
 expect(screen.queryByText('Plan to investigate later')).not.toBeInTheDocument();
});
