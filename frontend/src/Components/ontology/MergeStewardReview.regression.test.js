import React from 'react';
import {render,screen,fireEvent,cleanup,act} from '@testing-library/react';
import MergeStewardReview from '../../Components/ontology/MergeStewardReview.js';
import {ontologyMergeAgent} from '../../services/ontologyMergeAgent.js';
vi.mock('../../services/ontologyMergeAgent.js',()=>({ontologyMergeAgent:{evaluate:vi.fn(()=>new Promise(()=>{}))}}));
afterEach(cleanup);
test('OJ-03 regression: edits do not submit work and repeated clicks submit only one assessment',()=>{
 const onReview=vi.fn();const view=render(<MergeStewardReview enabled previewId="plan" reviewer="A" reviewKey="A" onReview={onReview}/>);
 view.rerender(<MergeStewardReview enabled previewId="plan" reviewer="Al" reviewKey="Al" onReview={onReview}/>);
 view.rerender(<MergeStewardReview enabled previewId="plan" reviewer="Ali" reviewKey="Ali" onReview={onReview}/>);
 expect(ontologyMergeAgent.evaluate).not.toHaveBeenCalled();
 const button=screen.getByRole('button',{name:'Run Steward assessment'});
 fireEvent.click(button);fireEvent.click(button);
 expect(ontologyMergeAgent.evaluate).toHaveBeenCalledTimes(1);
 expect(ontologyMergeAgent.evaluate).toHaveBeenCalledWith('plan','Ali');
});

test('a validation hold invalidates a pending assessment even when the preview ID is unchanged',async()=>{
 let finish;ontologyMergeAgent.evaluate.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 const onReview=vi.fn();const view=render(<MergeStewardReview enabled previewId="plan" reviewer="Steward" reviewKey="same" onReview={onReview}/>);
 fireEvent.click(screen.getByRole('button',{name:'Run Steward assessment'}));
 view.rerender(<MergeStewardReview enabled={false} previewId="plan" reviewer="Steward" reviewKey="same" onReview={onReview}/>);
 await act(async()=>{finish({runId:'old-run',result:{governance:{overall_verdict:'APPROVED'}}});});
 expect(onReview).toHaveBeenLastCalledWith(null);
 expect(screen.queryByText(/Steward checks passed/)).toBeNull();
});
