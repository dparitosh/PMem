import React from 'react';
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react';
import { vi, afterEach, test, expect } from 'vitest';
const state = vi.hoisted(() => ({ rows:[], taxonomy:vi.fn(), dictionary:vi.fn(), mappings:vi.fn() }));
vi.mock('../contexts/OntologyContext', () => ({useOntologies:()=>({ontologies:state.rows,loading:false,error:null})}));
vi.mock('../widgets/DataGridWidget', () => ({default:({title,rows=[]})=><section aria-label={title} data-count={rows.length}/> }));
vi.mock('../services/apiClient', async () => {
  const actual = await vi.importActual('../services/apiClient');
  return {...actual, API_METHODS:{...actual.API_METHODS,ontology:{...actual.API_METHODS.ontology,getTaxonomy:state.taxonomy,getDataDictionary:state.dictionary,getMappings:state.mappings}}};
});
import OntologyMapper, {ProtegeOntologyBrowser, collectBridgeTargetOptions, normalizeBridgeMappingRow} from './OntologyMapper';

test('bridge targets preserve distinct IRIs for duplicate labels',()=>{
 const rows=collectBridgeTargetOptions({classes:[{iri:'urn:a',label:'Part'},{iri:'urn:A',label:'Part'},{iri:'urn:b',label:'Part'}]});
 expect(rows.map(row=>row.value)).toEqual(['urn:a','urn:A','urn:b']);
 expect(normalizeBridgeMappingRow({confidence:null}).confidence).toBeNull();
 expect(normalizeBridgeMappingRow({confidence:2}).confidence).toBeNull();
 expect(normalizeBridgeMappingRow({confidence:.72}).confidence).toBe(.72);
});

test('vocabulary timeout does not hide instance agents or the ontology merge workspace', async()=>{
 window.location.hash='#/ontology?target=target-id';
 state.rows=[{ontology_id:'source-id',prefix:'source',label:'Source'},{ontology_id:'target-id',prefix:'target',label:'Target'}];
 state.dictionary.mockRejectedValue(new Error('Dictionary unavailable'));
 state.mappings.mockRejectedValue(new Error('Vocabulary timed out'));
 state.taxonomy.mockResolvedValue({data:{nodes:[],edges:[]}});
 render(<OntologyMapper/>);
 await screen.findByRole('option',{name:/Target.*target-id/});
 fireEvent.click(screen.getByRole('tab',{name:'2. Semantic Bridge'}));
 expect(await screen.findByText(/Vocabulary loading failed/)).toBeVisible();
 expect(screen.getByRole('heading',{name:'Automated instance mapping'})).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'Merge two ontologies'}));
 expect(await screen.findByRole('combobox',{name:'Source ontology'})).toBeVisible();
 expect(screen.getByRole('region',{name:'Agent mapping proposals'})).toBeVisible();
 expect(screen.getByRole('button',{name:'Review merge plan'})).toBeVisible();
});
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
