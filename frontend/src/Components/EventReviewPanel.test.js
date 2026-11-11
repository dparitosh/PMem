import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {vi} from 'vitest';
import EventReviewPanel from './EventReviewPanel';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{speedReviews:vi.fn(),speedReview:vi.fn()}}));
vi.mock('./AgentProposalPanel',()=>({default:({context})=><p>Selected agent context: {context.reconciliation_id}</p>}));
beforeEach(()=>{vi.clearAllMocks();api.speedReviews.mockResolvedValue({data:{reconciliations:[{reconciliation_id:'one',standard:'ap242',status:'reconciling',counts:{events:2}}],next_offset:null}});});

test('uses a retained selection and separates semantic validation from approval',async()=>{
 const onSelect=vi.fn();api.speedReview.mockResolvedValue({data:{reconciliation_id:'one',status:'ready_for_approved_publication',advisory_only:true,semantic_conforms:true,publication_verified:false}});
 render(<EventReviewPanel onSelect={onSelect}/>);await screen.findByRole('option',{name:/ap242/});
 fireEvent.change(screen.getByRole('combobox',{name:'Retained event review'}),{target:{value:'one'}});
 expect(await screen.findByText('Passed for this retained partition')).toBeInTheDocument();expect(screen.getByText('Not published')).toBeInTheDocument();
 expect(onSelect).toHaveBeenLastCalledWith('one');expect(screen.getByText('Selected agent context: one')).toBeInTheDocument();
});

test('reconnect aborts a late inspection before it can restore companion context',async()=>{
 let resolve;api.speedReview.mockImplementation(()=>new Promise(r=>{resolve=r;}));const onSelect=vi.fn();render(<EventReviewPanel onSelect={onSelect}/>);
 await screen.findByRole('option',{name:/ap242/});fireEvent.change(screen.getByRole('combobox',{name:'Retained event review'}),{target:{value:'one'}});
 fireEvent(window,new Event('depo:session-replaced'));resolve({data:{reconciliation_id:'one',status:'published',advisory_only:true}});
 await waitFor(()=>expect(api.speedReviews).toHaveBeenCalledTimes(2));expect(screen.queryByText('Verified publication receipt retained')).toBeNull();expect(onSelect).not.toHaveBeenCalledWith('one');
});

test('a foreign returned identity is held instead of being sent to an agent',async()=>{
 api.speedReview.mockResolvedValue({data:{reconciliation_id:'different',advisory_only:true}});const onSelect=vi.fn();render(<EventReviewPanel onSelect={onSelect}/>);
 await screen.findByRole('option',{name:/ap242/});fireEvent.change(screen.getByRole('combobox',{name:'Retained event review'}),{target:{value:'one'}});
 expect(await screen.findByRole('alert')).toHaveTextContent('identity');expect(onSelect).not.toHaveBeenCalledWith('one');
});
