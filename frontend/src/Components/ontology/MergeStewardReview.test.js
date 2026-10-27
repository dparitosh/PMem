import React from 'react';
import {render,screen,waitFor,fireEvent} from '@testing-library/react';
import {ontologyMergeAgent} from '../../services/ontologyMergeAgent';
import MergeStewardReview from './MergeStewardReview';
vi.mock('../../services/ontologyMergeAgent',()=>({ontologyMergeAgent:{evaluate:vi.fn()}}));
const report={overall_verdict:'REJECTED',audit_id:'audit',profile:'imported_standard',recommended_version_bump:'MAJOR',violations_and_remediations:[{subject_uri:'urn:Design',issue_category:'IDENTITY_CONFLATION',severity:'BLOCKER',diagnosis:'Design and physical item require review',action_taken:'QUARANTINED'}],coverage:{foundation_alignment:'not_configured'},metrics:{findings:1,quarantined_subjects:1}};

test('Steward findings explain the hold and do not grant publication',async()=>{
 ontologyMergeAgent.evaluate.mockResolvedValue({runId:'steward-run',result:{governance:report}});
 const onReview=vi.fn();
 render(<MergeStewardReview enabled previewId="saved" reviewKey="key" reviewer="reviewer" onReview={onReview}/>);
 fireEvent.click(screen.getByRole('button',{name:'Run Steward assessment'}));
 expect(await screen.findByText('Publication held — review the findings below')).toBeVisible();
 expect(screen.getByText('Design and physical item require review')).toBeInTheDocument();
 expect(onReview).toHaveBeenLastCalledWith(expect.objectContaining({key:'key',status:'completed',runId:'steward-run'}));
 expect(ontologyMergeAgent.evaluate).toHaveBeenCalledWith('saved','reviewer');
});

test('a late assessment cannot attach to a different selected plan',async()=>{
 let finish;
 ontologyMergeAgent.evaluate.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValue({runId:'new-run',result:{governance:{...report,audit_id:'new'}}});
 const onReview=vi.fn();
 const view=render(<MergeStewardReview enabled previewId="old" reviewKey="old" reviewer="reviewer" onReview={onReview}/>);
 fireEvent.click(screen.getByRole('button',{name:'Run Steward assessment'}));
 view.rerender(<MergeStewardReview enabled previewId="new" reviewKey="new" reviewer="reviewer" onReview={onReview}/>);
 finish({runId:'old-run',result:{governance:report}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Run Steward assessment'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Run Steward assessment'}));
 await waitFor(()=>expect(onReview).toHaveBeenLastCalledWith(expect.objectContaining({key:'new',status:'completed'})));
});
