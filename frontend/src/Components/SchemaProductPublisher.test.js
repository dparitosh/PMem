import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import SchemaProductPublisher from './SchemaProductPublisher';
import { apiClient } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { post: vi.fn() } }));
const recovery = vi.hoisted(() => ({ scope: 'deployment-a' }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: () => 'test-token', publicationRecoveryScope: () => recovery.scope }));
vi.mock('../config', () => ({ buildSemanticServiceUrl: (_service, path) => path }));
vi.mock('../services/analyticsProductDraft', () => ({ publicationFromDraft: () => ({ product_id: 'a' }), isDefinitivePublicationRejection: () => false }));
vi.mock('@siemens/ix-react', () => ({ IxButton: ({ children, ...props }) => <button {...props}>{children}</button> }));
beforeEach(() => { sessionStorage.clear(); recovery.scope = 'deployment-a'; });


const draft={name:'Retained evidence'};
function retainPending(value=draft){
 const payload={product_id:'a',version:'1.0.0',idempotency_key:'retained-original'};
 sessionStorage.setItem(`depo:pending-publication:${JSON.stringify(['deployment-a',value])}`,JSON.stringify({scope:'deployment-a',payload,draft:value,fields:{name:value.name}}));
 return payload;
}
test('new publication has one CR/CO submission route and no manual approver',async()=>{
 apiClient.post.mockResolvedValue({data:{valid:true}});render(<SchemaProductPublisher draft={draft}/>);
 expect(screen.queryByLabelText('Approver')).not.toBeInTheDocument();
 expect(screen.queryByText('Approve and publish evidence')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Validate publication contract'));
 await screen.findByText('Contract valid. Steward approval is still required.');
 expect(screen.queryByText('Retry same publication')).not.toBeInTheDocument();
 expect(apiClient.post.mock.calls.every(([url])=>!url.endsWith('/publish'))).toBe(true);
});
for(const lost of [false,true])test(`central release submission retains scope, lost response: ${lost}`,async()=>{
 apiClient.post.mockReset();apiClient.post.mockImplementation(async url=>{
  if(url.endsWith('/preview'))return {data:{valid:true}};
  if(lost)throw new Error('Connection interrupted');
  return {data:{product_version:'a:undefined'}};
 });
 const published=vi.fn();render(<SchemaProductPublisher draft={draft} onPublished={published}/>);
 fireEvent.click(screen.getByText('Validate publication contract'));await screen.findByText('Contract valid. Steward approval is still required.');
 fireEvent.change(screen.getByLabelText('Business reason for release review'),{target:{value:'Reviewed retained artifacts'}});
 fireEvent.click(screen.getByText('Submit release for review'));
 await screen.findByRole('link',{name:'Inspect release request in Change Control'});
 expect(apiClient.post.mock.calls.some(([url])=>url.endsWith('/change-requests/submit'))).toBe(true);
 expect(apiClient.post.mock.calls.some(([url])=>url.endsWith('/publish'))).toBe(false);
 expect(published).not.toHaveBeenCalled();expect(screen.getByLabelText('Product name')).toBeDisabled();
});
for(const refresh of ['session','unmount','draft'])test(`legacy uncertain outcome preserves exact payload across ${refresh}`,async()=>{
 const payload=retainPending();apiClient.post.mockReset();apiClient.post.mockRejectedValue(new Error('Lost response'));
 let view=render(<SchemaProductPublisher draft={draft}/>);
 fireEvent.click(await screen.findByText('Retry same publication'));await screen.findByText('Lost response');
 if(refresh==='session')fireEvent(window,new Event('depo:session-expired'));
 if(refresh==='unmount'){view.unmount();view=render(<SchemaProductPublisher draft={draft}/>);}
 if(refresh==='draft')view.rerender(<SchemaProductPublisher draft={{name:'Changed draft'}}/>);
 fireEvent.click(await screen.findByText('Retry same publication'));
 await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(2));
 expect(apiClient.post.mock.calls.map(call=>call[1])).toEqual([payload,payload]);
 expect(screen.getByLabelText('Product name')).toHaveValue(draft.name);
});
test('successful legacy reconciliation clears its receipt and never enables a new direct publication',async()=>{
 retainPending();apiClient.post.mockReset();apiClient.post.mockResolvedValue({data:{product_id:'a',version:'1.0.0',status:'published'}});
 const view=render(<SchemaProductPublisher draft={draft}/>);fireEvent.click(await screen.findByText('Retry same publication'));
 await screen.findByText(/a@1.0.0: published/);expect(sessionStorage.length).toBe(0);
 view.rerender(<SchemaProductPublisher draft={{name:'Next'}}/>);
 expect(screen.getByLabelText('Product name')).toHaveValue('Next');expect(screen.queryByText('Retry same publication')).not.toBeInTheDocument();
});
test('another deployment cannot recover a retained publication',()=>{
 retainPending();recovery.scope='deployment-b';render(<SchemaProductPublisher draft={draft}/>);
 expect(screen.queryByText('Retry same publication')).not.toBeInTheDocument();
});
for(const change of ['root','dependencies','paths'])test(`changing ${change} invalidates previously inspected evidence`,async()=>{
 apiClient.post.mockReset();apiClient.post.mockImplementation(async url=>({data:url.endsWith('/inspect')?{data_product_draft:{name:'A'}}:{valid:true}}));
 render(<SchemaProductPublisher draft={draft}/>);fireEvent.click(screen.getByText('Inspect an XSD with dependency files'));
 fireEvent.change(screen.getByLabelText('Root XSD'),{target:{files:[new File(['a'],'a.xsd')]}});
 fireEvent.click(screen.getByText('Inspect schema set'));await screen.findByLabelText('Product name');
 fireEvent.click(screen.getByText('Validate publication contract'));await screen.findByText('Contract valid. Steward approval is still required.');
 if(change==='root')fireEvent.change(screen.getByLabelText('Root XSD'),{target:{files:[new File(['b'],'b.xsd')]}});
 if(change==='dependencies')fireEvent.change(screen.getByLabelText('Dependency XSD files'),{target:{files:[new File(['b'],'b.xsd')]}});
 if(change==='paths')fireEvent.change(screen.getByLabelText(/Relative paths/),{target:{value:'types/b.xsd'}});
 expect(screen.queryByText('Validate publication contract')).not.toBeInTheDocument();expect(screen.getByText(/Inspect the schema set again/)).toBeVisible();
});
