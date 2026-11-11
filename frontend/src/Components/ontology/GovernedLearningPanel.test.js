import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import GovernedLearningPanel from './GovernedLearningPanel';
vi.mock('../../services/serviceAuth',()=>({getCredentialProfile:()=> 'fixture-key'}));
const preview={candidates:[{candidate_id:'C',source_term:'Part',ontology_term:'Physical Part'}]};
const publication={job_id:'P',status:'published',approved_ids:['C']};
const support=(id='model')=>({data:{ontology_id:id,import_task_id:'import',lessons:[],advisory_only:true}});
function api(){return {support:vi.fn().mockResolvedValue(support()),outcome:vi.fn(),prepare:vi.fn(),review:vi.fn()};}
function fill(){
 fireEvent.change(screen.getByLabelText('Review name'),{target:{value:'Reviewer'}});
 fireEvent.change(screen.getByLabelText('Published mapping'),{target:{value:'C'}});
 fireEvent.change(screen.getByLabelText('Review evidence'),{target:{value:'Checked drawing and target meaning'}});
}
test('feedback, lesson preparation and approval are distinct explicit actions',async()=>{
 const client=api();
 client.outcome.mockResolvedValue({data:{kind:'outcome',outcome_id:'O',publication_id:'P',candidate_id:'C',result:'confirmed'}});
 client.prepare.mockResolvedValue({data:{kind:'lesson',lesson_id:'L',outcome_ids:['O'],status:'pending_review',review_hint:'Recheck current source',measurements:{assessments:1}}});
 client.review.mockResolvedValue({data:{kind:'lesson',lesson_id:'L',status:'approved',review_hint:'Recheck current source',measurements:{assessments:1}}});
 render(<GovernedLearningPanel ontologyId="model" importTaskId="import" preview={preview} publication={publication} api={client}/>);
 await screen.findByText('No approved hints for the current model revision.');fill();
 fireEvent.click(screen.getByRole('button',{name:'Save mapping feedback'}));
 fireEvent.click(screen.getByRole('button',{name:'Save mapping feedback'}));
 await screen.findByText(/Feedback retained/);expect(client.outcome).toHaveBeenCalledTimes(1);expect(client.prepare).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Prepare review hint'}));
 await screen.findByText(/Review state: pending_review/);expect(client.review).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText('Approval or revocation reason'),{target:{value:'Approved for advisory reuse'}});
 fireEvent.click(screen.getByRole('button',{name:'Approve review hint'}));
 await screen.findByRole('button',{name:'Revoke review hint'});expect(client.review).toHaveBeenCalledTimes(1);
});
test('switching source cancels late feedback and clears the old outcome',async()=>{
 const client=api();let finish,signal;
 client.outcome.mockImplementation((_body,s)=>{signal=s;return new Promise(resolve=>{finish=resolve;});});
 const view=render(<GovernedLearningPanel ontologyId="model" importTaskId="import" preview={preview} publication={publication} api={client}/>);
 await screen.findByText('No approved hints for the current model revision.');fill();fireEvent.click(screen.getByRole('button',{name:'Save mapping feedback'}));
 client.support.mockResolvedValue(support('other'));
 view.rerender(<GovernedLearningPanel ontologyId="other" importTaskId="import" api={client}/>);
 await act(async()=>finish({data:{kind:'outcome',outcome_id:'O',publication_id:'P',candidate_id:'C'}}));
 expect(signal.aborted).toBe(true);expect(screen.queryByText(/Feedback retained/)).toBeNull();
});
test('wrong-source hints are rejected and write controls stay unavailable without publication',async()=>{
 const client=api();client.support.mockResolvedValue(support('other'));
 render(<GovernedLearningPanel ontologyId="model" importTaskId="import" api={client}/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('selected source');
 expect(screen.queryByRole('button',{name:'Save mapping feedback'})).toBeNull();
});
