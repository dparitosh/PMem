import React from 'react';
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react';
import { vi, afterEach, test, expect } from 'vitest';
const state = vi.hoisted(() => ({ rows:[], taxonomy:vi.fn(), dictionary:vi.fn(), mappings:vi.fn(), preview:vi.fn(), status:vi.fn() }));
vi.mock('../services/ontologyMergeAgent',()=>({ontologyMergeAgent:{preview:state.preview,apply:vi.fn()}}));
vi.mock('../services/serviceAuth',async()=>({...await vi.importActual('../services/serviceAuth'),getCredentialProfile:()=> 'test-token'}));
vi.mock('../contexts/OntologyContext', () => ({useOntologies:()=>({ontologies:state.rows,loading:false,error:null})}));
vi.mock('../widgets/DataGridWidget', () => ({default:({title,rows=[]})=><section aria-label={title} data-count={rows.length}/> }));
vi.mock('../services/apiClient', async () => {
  const actual = await vi.importActual('../services/apiClient');
  return {...actual, API_METHODS:{...actual.API_METHODS,ontology:{...actual.API_METHODS.ontology,governedMergeStatus:state.status,getTaxonomy:state.taxonomy,getDataDictionary:state.dictionary,getMappings:state.mappings}}};
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
test('background merge shows mappings while validation holds approval and resumes a retained review',async()=>{
 window.location.hash='#/ontology?target=target-id';
 state.rows=[{ontology_id:'source-id',prefix:'source',label:'Source'},{ontology_id:'target-id',prefix:'target',label:'Target'}];
 state.taxonomy.mockResolvedValue({data:{nodes:[],edges:[]}});
 const plan={preview_id:'job-1',background_validation:true,job_status:'validating',source_ontology_ids:['source-id','target-id'],
   entity_suggestions:[],semantic_checks:{shacl_conforms:null},conflicts:[],publish_recommended:false};
 state.preview.mockResolvedValue({runId:'agent-1',result:{...plan,job_status:'queued'}});
 state.status.mockResolvedValue({data:plan});
 const view=render(<OntologyMapper/>);
 await screen.findByRole('option',{name:/Target.*target-id/});
 fireEvent.click(screen.getByRole('tab',{name:'2. Semantic Bridge'}));
 fireEvent.click(screen.getByRole('tab',{name:'Merge two ontologies'}));
 fireEvent.change(screen.getByRole('combobox',{name:'Source ontology'}),{target:{value:'source-id'}});
 const approver=screen.getByPlaceholderText('name or service principal');
 fireEvent.change(approver,{target:{value:'pmem-ui-test'}});
 fireEvent.click(screen.getByRole('button',{name:'Review merge plan'}));
 await screen.findByText(/Mappings are ready for review/);
 expect(state.preview.mock.calls[0][1].background).toBe(true);
 expect(screen.getByRole('button',{name:/Approve.*publish/i})).toBeDisabled();
 expect(screen.getByText(/SHACL: Pending/)).toBeInTheDocument();
 state.status.mockResolvedValueOnce({data:plan}).mockResolvedValueOnce({data:{...plan,job_status:'failed',job_error:'Validation exceeded its deadline'}});
 fireEvent.click(screen.getByRole('button',{name:/Resume retained review/}));
 await screen.findAllByText(/Validation exceeded its deadline/);
 expect(screen.getByRole('button',{name:/Approve.*publish/i})).toBeDisabled();
 state.status.mockResolvedValue({data:plan});
 view.unmount();
 render(<OntologyMapper/>);
 await screen.findByRole('option',{name:/Target.*target-id/});
 fireEvent.click(screen.getByRole('tab',{name:'2. Semantic Bridge'}));
 fireEvent.click(screen.getByRole('tab',{name:'Merge two ontologies'}));
 fireEvent.change(screen.getByRole('combobox',{name:'Source ontology'}),{target:{value:'source-id'}});
 fireEvent.click(screen.getByRole('button',{name:/Resume retained review/}));
 await screen.findByText(/Mappings are ready for review/);
 expect(state.status).toHaveBeenCalledWith('job-1',expect.any(Object));
 state.status.mockResolvedValueOnce({data:plan}).mockResolvedValueOnce({data:{...plan,job_status:'completed',
   semantic_checks:{shacl_conforms:false,report:'Validation findings',report_summary:{total_results:3,
     by_severity:{'http://www.w3.org/ns/shacl#Violation':3},text_truncated:true,
     profiles:[{profile:'editorial_asserted',conforms:false,total_results:3}]}}}});
 fireEvent.click(screen.getByRole('button',{name:/Resume retained review/}));
 await screen.findByText(/Semantic validation completed with blocking findings/);
 fireEvent.click(screen.getByText('Semantic validation evidence',{exact:true}));
 expect(screen.getByText(/Findings: 3/)).toBeVisible();
 expect(screen.getByText(/Authored ontology metadata: Needs review/)).toBeVisible();
 expect(screen.getByRole('button',{name:/Approve.*publish/i})).toBeDisabled();
});
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
