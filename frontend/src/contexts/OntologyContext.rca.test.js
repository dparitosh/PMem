// Progressive registry loading regression.
import React from 'react';
import {act,cleanup,render,screen} from '@testing-library/react';
import {expect,test,vi,afterEach} from 'vitest';
import {OntologyProvider,useOntologies} from './OntologyContext';
import {apiClient} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn()}}));
vi.mock('../config',()=>({buildUrl:p=>p}));
function State(){const s=useOntologies();return <><p>{s.ontologies.map(o=>o.name).join(',')||'No visible records'}</p><span role="status">{s.warning}</span></>;}
afterEach(cleanup);
test('RCA-04: successful catalog appears before ingestion registry settles',async()=>{
 let finish;
 apiClient.get.mockImplementation(path=>path.startsWith('/api/v1/ontologies')
  ?Promise.resolve({data:{ontologies:[{ontology_id:'one',name:'Ready catalog'}]}})
  :new Promise(resolve=>{finish=resolve;}));
 render(<OntologyProvider><State/></OntologyProvider>);
 await act(async()=>{});
 expect(screen.queryByText('No visible records')).toBeNull();
 expect(screen.getByText('Ready catalog')).toBeVisible();
 expect(screen.getByRole('status')).toHaveTextContent('completeness is not yet verified');
 await act(async()=>finish({data:{ontologies:[]}}));
 expect(screen.getByText('Ready catalog')).toBeVisible();
 expect(screen.getByRole('status')).toBeEmptyDOMElement();
});

test('partial failure keeps ready rows and exposes the failed source',async()=>{
 let fail;
 apiClient.get.mockImplementation(path=>path.startsWith('/api/v1/ontologies')
  ?Promise.resolve({data:{ontologies:[{ontology_id:'one',name:'Ready catalog'}]}})
  :new Promise((_resolve,reject)=>{fail=reject;}));
 render(<OntologyProvider><State/></OntologyProvider>);
 await act(async()=>{});
 await act(async()=>fail(new Error('offline')));
 expect(screen.getByText('Ready catalog')).toBeVisible();
 expect(screen.getByRole('status')).toHaveTextContent('Partial ontology list: Ingestion registry');
});

test('late source completion cannot repopulate a replaced session',async()=>{
 const finish=[];
 apiClient.get.mockImplementation(()=>new Promise(resolve=>finish.push(resolve)));
 render(<OntologyProvider><State/></OntologyProvider>);
 await act(async()=>window.dispatchEvent(new Event('depo:session-replaced')));
 await act(async()=>finish[0]({data:{ontologies:[{ontology_id:'old',name:'Old identity'}]}}));
 expect(screen.queryByText('Old identity')).toBeNull();
});

test('same-session refresh retains native rows until native source responds',async()=>{
 apiClient.get.mockImplementation(path=>Promise.resolve({data:{ontologies:path.startsWith('/api/v1/ontologies')
  ?[{ontology_id:'native',name:'Native selection'}]:[]}}));
 render(<OntologyProvider><State/></OntologyProvider>);
 await act(async()=>{});
 let finish;
 apiClient.get.mockImplementation(path=>path.startsWith('/api/v1/ontologies')
  ?new Promise(resolve=>{finish=resolve;}):Promise.resolve({data:{ontologies:[]}}));
 await act(async()=>window.dispatchEvent(new Event('depo:access-verified')));
 expect(screen.getByText('Native selection')).toBeVisible();
 await act(async()=>finish({data:{ontologies:[{ontology_id:'native',name:'Native selection'}]}}));
 expect(screen.getByText('Native selection')).toBeVisible();
});
