import React from 'react';
import {render,screen,fireEvent,act,waitFor} from '@testing-library/react';
import {vi,it,expect,beforeEach} from 'vitest';
import {apiClient} from '../services/apiClient';
import ChangeControlPage from './ChangeControlPage';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn()}}));
const record={record_key:'pipeline:r',identifier:'r',title:'Validation run',category:'Data Flow run',owner_service:'dataPipeline',review_state:'Evidence only; not approval',execution_state:'Completed',delivery_state:'Not verified',workspace:'#/data-flow/r',evidence:{run_id:'r'},read_only:true};
const response=rows=>({data:{records:rows,coverage:[{source:'pipeline',status:'available'}],partial:false}});
beforeEach(()=>{vi.clearAllMocks();window.history.replaceState(null,'','#/change-control?view=workflows');});
it('separates completed execution from authorization and links to the owning workflow',async()=>{
 apiClient.get.mockImplementation(url=>Promise.resolve(url.endsWith('/pipeline/r')?{data:record}:response([record])));render(<ChangeControlPage/>);
 await screen.findByText('Validation run');
 expect(screen.getByText('Evidence only; not approval')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'View change Validation run'}));
 expect(await screen.findByRole('link',{name:'Open owning workflow'})).toHaveAttribute('href','#/data-flow/r');
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
 await screen.findByText(/No workflow records/);
 fireEvent.change(screen.getByLabelText('Workspace'),{target:{value:'products'}});
 await waitFor(()=>expect(apiClient.get.mock.calls.at(-1)[1].params).toEqual({source:'products',limit:25,offset:0}));
});

it('opens an exact retained review outside the current history window',async()=>{
 window.history.replaceState(null,'','#/change-control?source=pipeline&record=r');
 apiClient.get.mockImplementation(url=>Promise.resolve(url.endsWith('/pipeline/r')?{data:record}:response([])));
 const view=render(<ChangeControlPage/>);
 expect(await screen.findByLabelText('Selected change evidence')).toHaveTextContent('Validation run');
 expect(await screen.findByRole('link',{name:'Open owning workflow'})).toHaveAttribute('href','#/data-flow/r');
 view.unmount();window.history.replaceState(null,'','#/change-control?view=workflows');
});


it('shows request baseline and native release evidence without adding an approval command',async()=>{
 const dossier={request:{resource_type:'oslc_cm:ChangeRequest',state:'Retained proposal; review in owning workflow'},baseline:{status:'Exact retained source snapshot',currentness:'Not revalidated',members:[{identifier:'a',title:'Product vocabulary',artifact_sha256:'a'.repeat(64),workspace:'#/ontology?target=a'}]},release:{state:'No authorization recorded',execution_state:'Preview ready',delivery_state:'Not verified',authority:'Only the owning service can authorize and execute'}};
 const proposal={...record,source_kind:'merges',record_key:'merges:p',identifier:'p',title:'Merge proposal',dossier};
 apiClient.get.mockImplementation(url=>Promise.resolve(url.endsWith('/merges/p')?{data:proposal}:response([proposal])));
 render(<ChangeControlPage/>);await screen.findByText('Merge proposal');
 fireEvent.click(screen.getByRole('button',{name:'View change Merge proposal'}));
 expect(await screen.findByRole('heading',{name:'Change request (CR)'})).toBeVisible();
 expect(screen.getByRole('link',{name:'Product vocabulary'})).toHaveAttribute('href','#/ontology?target=a');
 expect(screen.getByText('Exact retained source snapshot')).toBeVisible();
 expect(screen.queryByRole('button',{name:/Approve|Execute release/})).toBeNull();
});

it('late dossier reads cannot replace a newer selection or reconnect context',async()=>{
 const next={...record,identifier:'next',record_key:'pipeline:next',title:'Next run'};
 let finish;apiClient.get.mockImplementation(url=>url.endsWith('/pipeline/r')?new Promise(resolve=>{finish=resolve;}):url.endsWith('/pipeline/next')?Promise.resolve({data:next}):Promise.resolve(response([record,next])));
 render(<ChangeControlPage/>);await screen.findByText('Validation run');
 fireEvent.click(screen.getByRole('button',{name:'View change Validation run'}));
 const old=apiClient.get.mock.calls.find(([url])=>url.endsWith('/pipeline/r'))[1].signal;
 fireEvent.click(screen.getByRole('button',{name:'View change Next run'}));
 await waitFor(()=>expect(screen.getByLabelText('Selected change evidence')).toHaveTextContent('Next run'));
 expect(old.aborted).toBe(true);
 await act(async()=>finish({data:record}));
 expect(screen.getByLabelText('Selected change evidence')).toHaveTextContent('Next run');
 fireEvent(window,new Event('depo:session-replaced'));
 expect(screen.queryByLabelText('Selected change evidence')).toBeNull();
});


it('retains exact selection and list offset through refresh, Close and history',async()=>{
 window.history.replaceState(null,'','#/change-control?view=workflows&source=all&offset=25&context=keep');
 apiClient.get.mockImplementation(url=>Promise.resolve(url.endsWith('/pipeline/r')?{data:record}:response([record])));
 const view=render(<ChangeControlPage/>);await screen.findByText('Validation run');
 fireEvent.click(screen.getByRole('button',{name:'View change Validation run'}));
 await screen.findByLabelText('Selected change evidence');
 const selectedRoute=window.location.hash;
 const params=new URLSearchParams(selectedRoute.split('?')[1]);
 expect(params.get('record')).toBe('r');expect(params.get('record_source')).toBe('pipeline');
 expect(params.get('source')).toBe('all');expect(params.get('offset')).toBe('25');expect(params.get('context')).toBe('keep');
 expect(apiClient.get.mock.calls.filter(([url])=>url.endsWith('/pipeline/r'))).toHaveLength(1);
 expect(apiClient.get.mock.calls.filter(([,options])=>options.params)).toHaveLength(1);
 view.unmount();render(<ChangeControlPage/>);await screen.findByLabelText('Selected change evidence');
 fireEvent.click(screen.getByRole('button',{name:'Close details'}));
 expect(screen.queryByLabelText('Selected change evidence')).toBeNull();
 expect(new URLSearchParams(window.location.hash.split('?')[1]).has('record')).toBe(false);
 expect(window.location.hash).toContain('offset=25');
 act(()=>{window.history.replaceState(null,'',selectedRoute);window.dispatchEvent(new PopStateEvent('popstate'));});
 expect(await screen.findByLabelText('Selected change evidence')).toHaveTextContent('Validation run');
});


it('separates numbered CR and CO registers from processing history',async()=>{
 window.history.replaceState(null,'','#/change-control');
 const request={...record,type:'oslc_cm:ChangeRequest',title:'Publish induction motor assembly',request_number:'CR-2026-000001',order_number:'CO-2026-000001'};
 apiClient.get.mockResolvedValue(response([record,request]));render(<ChangeControlPage/>);
 expect(await screen.findByText('CR-2026-000001')).toBeVisible();
 expect(screen.queryByText('Validation run')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Change orders',exact:true}));
 expect(screen.getByText('CO-2026-000001')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Workflow records',exact:true}));
 expect(screen.getByText('Validation run')).toBeVisible();
 expect(screen.queryByText('CR-2026-000001')).toBeNull();
});

it('returns to the exact mapping workspace and rejects external return destinations',async()=>{
 apiClient.get.mockResolvedValue(response([]));
 const target='#/ontology?view=alignment&mode=merge&merge_source=plm&target=mbse&merge_preview=plan';
 window.history.replaceState(null,'','#/change-control?return_to='+encodeURIComponent(target));
 const view=render(<ChangeControlPage/>);
 expect(screen.getByRole('link',{name:'← Return to mapping review'})).toHaveAttribute('href',target);
 view.unmount();window.history.replaceState(null,'','#/change-control?return_to='+encodeURIComponent('https://external.invalid/'));
 render(<ChangeControlPage/>);expect(screen.queryByRole('link',{name:'← Return to mapping review'})).toBeNull();
});


it('counts retained authority from the owning-service contract rather than review display text',async()=>{
  apiClient.get.mockResolvedValue(response([
    {...record,title:'Executed local load',review_state:'executed',authorization_kind:'Service authorization',authorization_actor:'verified-owner'},
    {...record,record_key:'pipeline:other',identifier:'other',title:'Display text alone',review_state:'Authorization retained',authorization_kind:'Not recorded',authorization_actor:'unverified'},
  ]));
  render(<ChangeControlPage/>);
  await screen.findByText('Executed local load');
  expect(screen.getByText('Authorizations retained').previousElementSibling).toHaveTextContent(/^1$/);
});
