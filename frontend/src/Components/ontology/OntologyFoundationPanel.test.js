import React from 'react';
import {render,screen,fireEvent,act} from '@testing-library/react';
import OntologyFoundationPanel from './OntologyFoundationPanel';
import {apiClient} from '../../services/apiClient';
vi.mock('../../services/apiClient',()=>({apiClient:{get:vi.fn()}}));
vi.mock('../../config',()=>({buildUrl:path=>path}));
const foundation={owl_dl:{available:true}};

test('verified inconsistency has a business-facing result and never a success label',async()=>{
 apiClient.get.mockImplementation(path=>Promise.resolve({data:path.endsWith('/foundation')?foundation:{ontology_id:'source',status:'inconsistent',consistency_verified:true,artifact_sha256:'abc',engine:'HermiT'}}));
 render(<OntologyFoundationPanel ontologyId="source"/>);
 await screen.findByText(/OWL-DL engine available/);
 fireEvent.click(screen.getByRole('button',{name:'Check OWL-DL consistency'}));
 expect(await screen.findByText('Logical inconsistency detected')).toBeVisible();
 expect(screen.queryByText('Consistent within checked scope')).toBeNull();
});

test('selection changes abort the old check and discard its late result',async()=>{
 let finish,signal;
 apiClient.get.mockImplementation((path,options)=>path.endsWith('/foundation')?Promise.resolve({data:foundation}):new Promise(resolve=>{finish=resolve;signal=options.signal;}));
 const {rerender}=render(<OntologyFoundationPanel ontologyId="first"/>);
 await screen.findByText(/OWL-DL engine available/);
 fireEvent.click(screen.getByRole('button',{name:'Check OWL-DL consistency'}));
 rerender(<OntologyFoundationPanel ontologyId="second"/>);
 expect(signal.aborted).toBe(true);
 await act(async()=>finish({data:{status:'consistent',consistency_verified:true}}));
 expect(screen.queryByText('Consistent within checked scope')).toBeNull();
});

test('unknown and missing engine never imply validation passed',async()=>{
 apiClient.get.mockResolvedValue({data:{owl_dl:{available:false}}});
 render(<OntologyFoundationPanel ontologyId="source"/>);
 await screen.findByText(/OWL-DL engine unavailable/);
 expect(screen.getByRole('button',{name:'Check OWL-DL consistency'})).toBeDisabled();
});
