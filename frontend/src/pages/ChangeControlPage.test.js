import React from 'react';
import {render,screen,fireEvent,act,waitFor} from '@testing-library/react';
import {vi,it,expect,beforeEach} from 'vitest';
import {apiClient} from '../services/apiClient';
import ChangeControlPage from './ChangeControlPage';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn()}}));
const record={record_key:'pipeline:r',identifier:'r',title:'Validation run',category:'Data Flow run',owner_service:'dataPipeline',review_state:'Evidence only; not approval',execution_state:'Completed',delivery_state:'Not verified',workspace:'#/data-flow/r',evidence:{run_id:'r'},read_only:true};
const response=rows=>({data:{records:rows,coverage:[{source:'pipeline',status:'available'}],partial:false}});
beforeEach(()=>vi.clearAllMocks());
it('separates completed execution from authorization and links to the owning workflow',async()=>{
 apiClient.get.mockResolvedValue(response([record]));render(<ChangeControlPage/>);
 await screen.findByText('Validation run');
 expect(screen.getByText('Evidence only; not approval')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Inspect Validation run'}));
 expect(screen.getByRole('link',{name:'Open owning workflow'})).toHaveAttribute('href','#/data-flow/r');
 expect(screen.queryByRole('button',{name:'Approve',exact:true})).toBeNull();
});
it('reports partial evidence and malformed responses without inventing an empty history',async()=>{
 apiClient.get.mockResolvedValueOnce({data:{records:[record],coverage:[{source:'products',status:'unavailable'}],partial:true}})
  .mockResolvedValueOnce({data:{records:[42],coverage:[]}});
 render(<ChangeControlPage/>);expect(await screen.findByRole('alert')).toHaveTextContent('Partial evidence');
 fireEvent.click(screen.getByRole('button',{name:'Refresh changes'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Invalid change evidence response');
 expect(screen.queryByText(/No retained change evidence was returned/)).toBeNull();
});
it('cancels stale session reads and does not show old records after reconnect',async()=>{
 let finish;apiClient.get.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValueOnce(response([{...record,title:'Current run'}]));
 const view=render(<ChangeControlPage/>);const old=apiClient.get.mock.calls[0][1].signal;
 fireEvent(window,new Event('depo:session-replaced'));
 await screen.findByText('Current run');expect(old.aborted).toBe(true);
 await act(async()=>finish(response([{...record,title:'Old run'}])));
 expect(screen.queryByText('Old run')).toBeNull();
 view.unmount();fireEvent(window,new Event('depo:access-verified'));
 expect(apiClient.get).toHaveBeenCalledTimes(2);
});
it('changing workspace scopes the request and cancels the previous source',async()=>{
 apiClient.get.mockResolvedValue(response([]));render(<ChangeControlPage/>);
 await screen.findByText(/No retained change evidence/);
 fireEvent.change(screen.getByLabelText('Workspace'),{target:{value:'products'}});
 await waitFor(()=>expect(apiClient.get.mock.calls.at(-1)[1].params).toEqual({source:'products',limit:25,offset:0}));
});
