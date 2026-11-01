import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import RdfSourceUpload from './RdfSourceUpload';
import {metadataRegistryAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({metadataRegistryAPI:{registerRdfSource:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'author-token'}));
beforeEach(()=>vi.resetAllMocks());
test('registers a selected file without IDs and prevents duplicate clicks',async()=>{
 let complete;api.registerRdfSource.mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));const registered=vi.fn();
 render(<RdfSourceUpload onRegistered={registered}/>);
 fireEvent.change(screen.getByLabelText('Source name'),{target:{value:'Parts'}});
 const file=new File(['<urn:p> <urn:n> "Part" .'],'parts.ttl',{type:'text/turtle'});
 fireEvent.change(screen.getByLabelText('RDF source file'),{target:{files:[file]}});
 const button=screen.getByRole('button',{name:'Register source draft'});fireEvent.click(button);fireEvent.click(button);
 expect(api.registerRdfSource).toHaveBeenCalledTimes(1);
 await act(async()=>complete({data:{asset:{name:'Parts'},source_id:'metadata:retained'}}));
 expect(registered).toHaveBeenCalledTimes(1);expect(await screen.findByText(/Registered Parts/)).toBeInTheDocument();
});
test('late registration response cannot overwrite a replaced session',async()=>{
 let complete;api.registerRdfSource.mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));const registered=vi.fn();render(<RdfSourceUpload onRegistered={registered}/>);
 fireEvent.change(screen.getByLabelText('Source name'),{target:{value:'Parts'}});
 fireEvent.change(screen.getByLabelText('RDF source file'),{target:{files:[new File(['data'],'parts.ttl')]}});
 fireEvent.click(screen.getByRole('button',{name:'Register source draft'}));
 act(()=>window.dispatchEvent(new Event('depo:session-replaced')));
 await act(async()=>complete({data:{asset:{name:'Parts'}}}));
 expect(registered).not.toHaveBeenCalled();expect(screen.getByText(/Access changed/)).toBeInTheDocument();
});
