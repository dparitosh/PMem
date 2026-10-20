import React from 'react';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { vi, afterEach, test, expect } from 'vitest';
const state = vi.hoisted(() => ({ rows:[], taxonomy:vi.fn() }));
vi.mock('../contexts/OntologyContext', () => ({useOntologies:()=>({ontologies:state.rows,loading:false,error:null})}));
vi.mock('../widgets/DataGridWidget', () => ({default:({title,rows=[]})=><section aria-label={title} data-count={rows.length}/> }));
vi.mock('../services/apiClient', async () => {
  const actual = await vi.importActual('../services/apiClient');
  return {...actual, API_METHODS:{...actual.API_METHODS,ontology:{...actual.API_METHODS.ontology,getTaxonomy:state.taxonomy}}};
});
import OntologyMapper, {ProtegeOntologyBrowser} from './OntologyMapper';
afterEach(()=>{cleanup();window.location.hash='';vi.clearAllMocks();});
test('active draft is retained alongside a published version with the same prefix', async()=>{
  window.location.hash='#/ontology?target=draft-id';
  state.rows=[{ontology_id:'published-id',prefix:'shared',label:'Published'},{ontology_id:'draft-id',prefix:'shared',label:'Draft'}];
  state.taxonomy.mockResolvedValue({data:{nodes:[],edges:[]}});
  render(<OntologyMapper/>);
  await waitFor(()=>expect(screen.getByRole('combobox',{name:'Active ontology'})).toHaveValue('draft-id'));
  expect(screen.getByRole('option',{name:/Draft.*draft-id/})).toBeInTheDocument();
  expect(screen.getByRole('option',{name:/Published.*published-id/})).toBeInTheDocument();
});
test('no active ontology means no taxonomy fetch or silently selected default',async()=>{
  window.location.hash='#/ontology';state.rows=[{ontology_id:'published-id',prefix:'shared',label:'Published'}];
  render(<OntologyMapper/>);
  await waitFor(()=>expect(screen.getByRole('option',{name:/Published/})).toBeInTheDocument());
  expect(screen.getByRole('combobox',{name:'Active ontology'})).toHaveValue('');
  expect(state.taxonomy).not.toHaveBeenCalled();
});
test('class inventory is independent of the 800 row hierarchy preview and excludes nonclasses',()=>{
 const nodes=Array.from({length:805},(_,i)=>({term_id:'urn:c'+i,label:'Class '+i,kind:'class',source:'rdf-class'}));
 nodes.push({term_id:'urn:expression',label:'Restriction must not count',kind:'restriction',source:'rdf-expression'});
 render(<ProtegeOntologyBrowser nodes={nodes} edges={[]} filter="" taxonomy={{nodes,edges:[]}} reasoning={null}/>);
 expect(screen.getByRole('region',{name:'Class Hierarchy (800 of 805 loaded classes)'})).toHaveAttribute('data-count','800');
 expect(screen.getByRole('region',{name:'Classes (805)'})).toHaveAttribute('data-count','805');
 expect(screen.getByText('805')).toBeInTheDocument();
});

test('an unavailable requested ID does not fall back to another ontology',async()=>{
 window.location.hash='#/ontology?target=missing-id';
 state.rows=[{ontology_id:'published-id',prefix:'shared',label:'Published'}];
 render(<OntologyMapper/>);
 await screen.findByRole('option',{name:'Unavailable ontology (missing-id)'});
 expect(screen.getByRole('combobox',{name:'Active ontology'})).toHaveValue('missing-id');
 expect(state.taxonomy).not.toHaveBeenCalled();
});
