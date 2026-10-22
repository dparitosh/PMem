import React from 'react';
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react';
import { vi, afterEach, test, expect } from 'vitest';
const state = vi.hoisted(() => ({ rows:[], taxonomy:vi.fn(), dictionary:vi.fn(), mappings:vi.fn(), preview:vi.fn(), status:vi.fn(), evaluate:vi.fn(async id=>({runId:'steward-run',result:{preview_id:id,governance:{audit_id:'audit',policy_sha256:'policy',overall_verdict:'APPROVED',profile:'imported_standard',recommended_version_bump:'MINOR',violations_and_remediations:[],metrics:{findings:0,quarantined_subjects:0},coverage:{foundation_alignment:'not_configured'}}}})) }));
vi.mock('../services/ontologyMergeAgent',()=>({ontologyMergeAgent:{preview:state.preview,evaluate:state.evaluate,apply:vi.fn()}}));
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
 expect(screen.getByRole('button',{name:'Generate mapping plan'})).toBeVisible();
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
 fireEvent.click(screen.getByRole('button',{name:'Generate mapping plan'}));
 await screen.findByText(/Mappings are ready for review/);
 expect(state.preview.mock.calls[0][1].background).toBe(true);
 expect(screen.getByRole('button',{name:/Approve.*publish/i})).toBeDisabled();
 expect(screen.getByText(/SHACL: Pending/)).toBeInTheDocument();
 state.status.mockResolvedValueOnce({data:plan}).mockResolvedValueOnce({data:{...plan,job_status:'failed',job_error:'Validation exceeded its deadline'}});
 fireEvent.click(screen.getByRole('button',{name:/Resume saved plan/}));
 await screen.findAllByText(/Validation exceeded its deadline/);
 expect(screen.getByRole('button',{name:/Approve.*publish/i})).toBeDisabled();
 state.status.mockResolvedValue({data:plan});
 view.unmount();
 render(<OntologyMapper/>);
 await screen.findByRole('option',{name:/Target.*target-id/});
 fireEvent.click(screen.getByRole('tab',{name:'2. Semantic Bridge'}));
 fireEvent.click(screen.getByRole('tab',{name:'Merge two ontologies'}));
 fireEvent.change(screen.getByRole('combobox',{name:'Source ontology'}),{target:{value:'source-id'}});
 fireEvent.click(screen.getByRole('button',{name:/Resume saved plan/}));
 await screen.findByText(/Mappings are ready for review/);
 expect(state.status).toHaveBeenCalledWith('job-1',expect.any(Object));
 state.status.mockResolvedValueOnce({data:plan}).mockResolvedValueOnce({data:{...plan,job_status:'completed',
   semantic_checks:{shacl_conforms:false,report:'Validation findings',report_summary:{total_results:3,
     by_severity:{'http://www.w3.org/ns/shacl#Violation':3},text_truncated:true,
     profiles:[{profile:'editorial_asserted',conforms:false,total_results:3}]}}}});
 fireEvent.click(screen.getByRole('button',{name:/Resume saved plan/}));
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
test('initial taxonomy loads a visible default without visiting vocabulary and respects clearing',async()=>{
  window.location.hash='#/ontology';state.rows=[{ontology_id:'published-id',prefix:'shared',label:'Published'}];
  state.taxonomy.mockResolvedValue({data:{nodes:[{term_id:'urn:Part',label:'Part',kind:'class',source:'rdf-class'}],edges:[]}});
  render(<OntologyMapper/>);
  await waitFor(()=>expect(screen.getByRole('combobox',{name:'Active ontology'})).toHaveValue('published-id'));
  await waitFor(()=>expect(state.taxonomy).toHaveBeenCalledWith('published-id',expect.objectContaining({signal:expect.any(AbortSignal)})));
  expect(await screen.findByRole('region',{name:'Classes (1)'})).toBeInTheDocument();
  expect(state.dictionary).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole('combobox',{name:'Active ontology'}),{target:{value:''}});
  await waitFor(()=>expect(screen.getByRole('combobox',{name:'Active ontology'})).toHaveValue(''));
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


test('taxonomy retries a failed first load without visiting another tab',async()=>{
 window.location.hash='#/ontology?target=target-id';
 state.rows=[{ontology_id:'target-id',prefix:'target',label:'Target'}];
 state.taxonomy.mockRejectedValueOnce(new Error('Temporarily unavailable')).mockResolvedValue({data:{nodes:[],edges:[]}});
 render(<OntologyMapper/>);
 fireEvent.click(await screen.findByRole('button',{name:'Retry taxonomy loading'}));
 await waitFor(()=>expect(state.taxonomy).toHaveBeenCalledTimes(2));
 await waitFor(()=>expect(screen.queryByRole('button',{name:'Retry taxonomy loading'})).not.toBeInTheDocument());
});

test('changing ontology discards the old taxonomy and ignores a late response',async()=>{
 window.location.hash='#/ontology?target=first';
 state.rows=[{ontology_id:'first',prefix:'same',label:'First'},{ontology_id:'second',prefix:'same',label:'Second'}];
 let resolveFirst;
 state.taxonomy.mockImplementation(id=> id==='first' ? new Promise(resolve=>{resolveFirst=resolve;}) : Promise.resolve({data:{nodes:[{term_id:'urn:second',label:'Second class',kind:'class',source:'rdf-class'}],edges:[]}}));
 render(<OntologyMapper/>);
 await waitFor(()=>expect(state.taxonomy).toHaveBeenCalledWith('first',expect.anything()));
 fireEvent.change(screen.getByRole('combobox',{name:'Active ontology'}),{target:{value:'second'}});
 expect(await screen.findByRole('region',{name:'Classes (1)'})).toBeInTheDocument();
 resolveFirst({data:{nodes:[],edges:[]}});
 await waitFor(()=>expect(screen.getByRole('region',{name:'Classes (1)'})).toBeInTheDocument());
 expect(screen.getByRole('combobox',{name:'Active ontology'})).toHaveValue('second');
});


test('selected merge mappings keep the evidence visible but block stale-plan publication',async()=>{
 window.location.hash='#/ontology?target=target-id';
 state.rows=[{ontology_id:'source-id',prefix:'source',label:'Source'},{ontology_id:'target-id',prefix:'target',label:'Target'}];
 state.taxonomy.mockResolvedValue({data:{nodes:[],edges:[]}});
 const candidate={source_iri:'urn:source:Part',target_iri:'urn:target:Part',source_label:'Source Part',target_label:'Target Part',kind:'Class',confidence_score:.9};
 const plan={preview_id:'current-plan',background_validation:true,job_status:'completed',publish_recommended:true,conflicts:[],entity_suggestions:[candidate],changes:{entity_mappings:[]}};
 state.preview.mockResolvedValue({runId:'agent-current',result:plan});
 render(<OntologyMapper/>);
 await screen.findByRole('option',{name:/Target.*target-id/});
 fireEvent.click(screen.getByRole('tab',{name:'2. Semantic Bridge'}));
 fireEvent.click(screen.getByRole('tab',{name:'Merge two ontologies'}));
 fireEvent.change(screen.getByLabelText('Reviewing steward'),{target:{value:'steward'}});
 fireEvent.click(screen.getByRole('button',{name:'Generate mapping plan'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Approve merge and publish'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Select for consolidation'}));
 expect(screen.getByText('Source Part')).toBeVisible();
 expect(screen.getByText('Selection needs validation')).toBeVisible();
 expect(screen.getByRole('button',{name:'Approve merge and publish'})).toBeDisabled();
 state.preview.mockResolvedValue({runId:'agent-revised',result:{...plan,preview_id:'revised-plan',changes:{entity_mappings:[candidate]}}});
 fireEvent.click(screen.getByRole('button',{name:'Validate selected mappings'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Approve merge and publish'})).toBeEnabled());
 expect(state.preview.mock.calls.at(-1)[1].entity_mappings).toEqual([{source_iri:candidate.source_iri,target_iri:candidate.target_iri}]);
 expect(screen.getByText('Selected mappings in this plan')).toBeVisible();
 fireEvent(window,new Event('depo:session-expired'));
 await waitFor(()=>expect(screen.queryByRole('button',{name:'Approve merge and publish'})).not.toBeEnabled());
});


test('an empty registry gives an import path rather than a service outage warning',async()=>{
 window.location.hash='#/ontology?view=alignment&mode=merge'; state.rows=[];
 render(<OntologyMapper/>);
 expect(await screen.findByRole('link',{name:'Import ontology versions'})).toHaveAttribute('href','#/import');
 expect(screen.queryByText('Ontology service unavailable · Show details')).not.toBeInTheDocument();
 expect(screen.getByText(/Register at least two ontology versions/)).toBeVisible();
});
