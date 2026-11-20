import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {vi} from 'vitest';
import EventReviewPanel from './EventReviewPanel';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{speedReviews:vi.fn(),speedReview:vi.fn(),definitions:vi.fn().mockResolvedValue({data:{definitions:[]}}),prepareEventJob:vi.fn()}}));
beforeEach(()=>{window.history.replaceState(null,'','#/data-flow?view=events');vi.clearAllMocks();api.speedReviews.mockResolvedValue({data:{reconciliations:[{reconciliation_id:'one',standard:'ap242',status:'reconciling',counts:{events:2}}],next_offset:null}});});

test('uses a retained selection and separates semantic validation from approval',async()=>{
 const onSelect=vi.fn();api.speedReview.mockResolvedValue({data:{reconciliation_id:'one',status:'ready_for_approved_publication',advisory_only:true,semantic_conforms:true,publication_verified:false}});
 render(<EventReviewPanel onSelect={onSelect}/>);await screen.findByRole('button',{name:'Review',exact:true});
 fireEvent.click(screen.getByRole('button',{name:'Review',exact:true}));
 expect(await screen.findByText('Passed for this retained partition')).toBeInTheDocument();expect(screen.getByText('Not published')).toBeInTheDocument();
 expect(onSelect).toHaveBeenLastCalledWith('one');expect(screen.getByRole('link',{name:'Open Agent Control'})).toHaveAttribute('href','#/admin?view=agents&source=data-flow&reconciliation_id=one');
 expect(screen.queryByText('Selected agent context: one')).toBeNull();
});

test('reconnect aborts a late inspection before it can restore companion context',async()=>{
 let resolve;api.speedReview.mockImplementation(()=>new Promise(r=>{resolve=r;}));const onSelect=vi.fn();render(<EventReviewPanel onSelect={onSelect}/>);
 await screen.findByRole('button',{name:'Review',exact:true});fireEvent.click(screen.getByRole('button',{name:'Review',exact:true}));
 fireEvent(window,new Event('depo:session-replaced'));resolve({data:{reconciliation_id:'one',status:'published',advisory_only:true}});
 await waitFor(()=>expect(api.speedReviews).toHaveBeenCalledTimes(2));expect(screen.queryByText('Verified publication receipt retained')).toBeNull();expect(onSelect).not.toHaveBeenCalledWith('one');
});

test('a foreign returned identity is held instead of being sent to an agent',async()=>{
 api.speedReview.mockResolvedValue({data:{reconciliation_id:'different',advisory_only:true}});const onSelect=vi.fn();render(<EventReviewPanel onSelect={onSelect}/>);
 await screen.findByRole('button',{name:'Review',exact:true});fireEvent.click(screen.getByRole('button',{name:'Review',exact:true}));
 expect(await screen.findByRole('alert')).toHaveTextContent('identity');expect(onSelect).not.toHaveBeenCalledWith('one');
});


test('malformed event evidence cannot activate the central control link',async()=>{
 api.speedReview.mockResolvedValue({data:{reconciliation_id:'one',advisory_only:true}});render(<EventReviewPanel onSelect={vi.fn()}/>);
 await screen.findByRole('button',{name:'Review',exact:true});fireEvent.click(screen.getByRole('button',{name:'Review',exact:true}));
 await screen.findByRole('alert');expect(screen.queryByRole('link',{name:'Open Agent Control'})).toBeNull();
});
test('empty retained list disables the selector and pagination',async()=>{
 api.speedReviews.mockResolvedValue({data:{reconciliations:[],next_offset:null}});render(<EventReviewPanel onSelect={vi.fn()}/>);
 await screen.findByText(/No event reviews are retained/);expect(screen.queryByRole('button',{name:'Review',exact:true})).toBeNull();expect(screen.getByRole('button',{name:'Next event reviews'})).toBeDisabled();
});


test('verified reconnect restores the URL selection only through a fresh evidence read',async()=>{
 window.history.replaceState(null,'','#/data-flow?view=events&reconciliation_id=one');
 api.speedReview.mockResolvedValue({data:{reconciliation_id:'one',status:'ready_for_approved_publication',advisory_only:true,semantic_conforms:true}});
 render(<EventReviewPanel onSelect={vi.fn()}/>);await screen.findByText('Passed for this retained partition');
 fireEvent(window,new Event('depo:access-verified'));await waitFor(()=>expect(api.speedReview).toHaveBeenCalledTimes(2));
 expect(await screen.findByText('Passed for this retained partition')).toBeInTheDocument();
});
test('same-page event navigation rejects a missing record without retaining previous evidence',async()=>{
 api.speedReview.mockImplementation(id=>id==='one'?Promise.resolve({data:{reconciliation_id:id,status:'ready',advisory_only:true,semantic_conforms:true}}):Promise.reject(new Error('Event not found')));
 window.history.replaceState(null,'','#/data-flow?view=events&reconciliation_id=one');render(<EventReviewPanel onSelect={vi.fn()}/>);await screen.findByText('Passed for this retained partition');
 window.history.replaceState(null,'','#/data-flow?view=events&reconciliation_id=missing');fireEvent(window,new HashChangeEvent('hashchange'));
 expect(await screen.findByRole('alert')).toHaveTextContent('Event not found');expect(screen.queryByRole('link',{name:'Open Agent Control'})).toBeNull();
});
