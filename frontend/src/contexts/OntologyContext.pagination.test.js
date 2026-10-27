import React from 'react';
import {act,render,screen,cleanup} from '@testing-library/react';
import {OntologyProvider,useOntologies} from '../contexts/OntologyContext.js';
import {apiClient} from '../services/apiClient.js';
vi.mock('../services/apiClient.js',()=>({apiClient:{get:vi.fn()}}));
vi.mock('../config.js',()=>({buildUrl:path=>path}));
function Status(){const state=useOntologies();return <p>{state.loading?'Audit loading':'Audit idle'}</p>;}
afterEach(()=>{cleanup();vi.useRealTimers();});
test('OJ-05 regression: empty advancing catalog pages have no page or whole-load budget',async()=>{
 let catalogCalls=0;
 apiClient.get.mockImplementation(path=>{
  if(!path.startsWith('/api/v1/ontologies'))return Promise.resolve({data:{ontologies:[]}});
  catalogCalls+=1;
  if(catalogCalls>25)return new Promise(()=>{});
  return Promise.resolve({data:{ontologies:[],next_offset:catalogCalls*200}});
 });
 render(<OntologyProvider><Status/></OntologyProvider>);
 await act(async()=>{});
 expect(catalogCalls).toBe(1);expect(screen.getByText('Audit idle')).toBeVisible();
});
