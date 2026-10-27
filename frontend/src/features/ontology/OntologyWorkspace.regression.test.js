import React from 'react';
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react';
import { vi, afterEach, test, expect } from 'vitest';
const state = vi.hoisted(() => ({ rows:[], taxonomy:vi.fn(), dictionary:vi.fn(), mappings:vi.fn(), preview:vi.fn(), status:vi.fn(), export:vi.fn(), evaluate:vi.fn(async id=>({runId:'steward-run',result:{preview_id:id,governance:{audit_id:'audit',policy_sha256:'policy',overall_verdict:'APPROVED',profile:'imported_standard',recommended_version_bump:'MINOR',violations_and_remediations:[],metrics:{findings:0,quarantined_subjects:0},coverage:{foundation_alignment:'not_configured'}}}})) }));
vi.mock('../../services/ontologyMergeAgent',()=>({ontologyMergeAgent:{preview:state.preview,evaluate:state.evaluate,apply:vi.fn()}}));
vi.mock('../../services/serviceAuth',async()=>({...await vi.importActual('../../services/serviceAuth'),getCredentialProfile:()=> 'test-token'}));
vi.mock('../../contexts/OntologyContext', () => ({useOntologies:()=>({ontologies:state.rows,loading:false,error:null})}));
vi.mock('../../widgets/DataGridWidget', () => ({default:({title,ariaLabel,rows=[]})=><section aria-label={ariaLabel || title} data-count={rows.length}/> }));
vi.mock('../../services/apiClient', async () => {
  const actual = await vi.importActual('../../services/apiClient');
  return {...actual, API_METHODS:{...actual.API_METHODS,ontology:{...actual.API_METHODS.ontology,exportRegistered:state.export,governedMergeStatus:state.status,getTaxonomy:state.taxonomy,getDataDictionary:state.dictionary,getMappings:state.mappings}}};
});
import OntologyMapper from "../../features/ontology/OntologyWorkspace.js";
import { ProtegeOntologyBrowser } from '../../features/ontology/OntologyBrowser';
import { collectBridgeTargetOptions, normalizeBridgeMappingRow } from '../../features/ontology/services/ontologyBridgePresentation';

const tasks={getTasks:vi.fn(),getStatus:vi.fn(),getPreview:vi.fn()};
afterEach(()=>{cleanup();vi.clearAllMocks();window.location.hash='';});

test('exports use the authenticated client and a failed download offers a visible error',async()=>{
 window.location.hash='#/ontology?target=target-id';state.rows=[{ontology_id:'target-id',prefix:'target',label:'Target'}];
 state.taxonomy.mockResolvedValue({data:{nodes:[],edges:[]}});
 state.export.mockRejectedValue(new Error('Export access rejected'));
 render(<OntologyMapper/>);
 fireEvent.click(await screen.findByRole('button',{name:'ttl'}));
 await screen.findByText('Export access rejected');
 expect(state.export).toHaveBeenCalledWith('target-id','ttl',expect.objectContaining({signal:expect.any(AbortSignal)}));
 expect(screen.queryByRole('link',{name:'ttl'})).toBeNull();
 expect(screen.getByRole('button',{name:'ttl'})).toBeEnabled();
});

test('credential replacement cancels an in-flight export before its content can download',async()=>{
 window.location.hash='#/ontology?target=target-id';state.rows=[{ontology_id:'target-id',prefix:'target',label:'Target'}];
 state.taxonomy.mockResolvedValue({data:{nodes:[],edges:[]}});
 let finish;state.export.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 render(<OntologyMapper/>);
 fireEvent.click(await screen.findByRole('button',{name:'ttl'}));
 const signal=state.export.mock.calls[0][2].signal;
 fireEvent(window,new Event('depo:session-replaced'));
 expect(signal.aborted).toBe(true);
 finish({data:new Blob(['retained'])});
 await waitFor(()=>expect(screen.getByRole('button',{name:'ttl'})).toBeEnabled());
 expect(screen.queryByText(/createObjectURL/)).toBeNull();
});
test('OJ-01 regression: successful mappings survive a failed dictionary and taxonomy fallback',async()=>{
 window.location.hash='#/ontology?target=target-id';state.rows=[{ontology_id:'target-id',prefix:'target',label:'Target'}];
 state.taxonomy.mockResolvedValueOnce({data:{nodes:[],edges:[]}}).mockRejectedValue(new Error('Fallback taxonomy unavailable'));
 state.dictionary.mockRejectedValue(new Error('Dictionary unavailable'));
 state.mappings.mockResolvedValue({data:{mapping_edges:[{source_term:'urn:AuditLabel',source_label:'AuditLabel',target_term:'urn:part',target_label:'Part',mapping_type:'mapsTo'}]}});
 render(<OntologyMapper/>);
 await screen.findByRole('option',{name:/Target/});
 fireEvent.click(screen.getByRole('tab',{name:'1. Mapping Vocabulary'}));
 await screen.findByText(/Term descriptions are unavailable/);
 expect(state.mappings).toHaveBeenCalled();
 expect(screen.getAllByText('AuditLabel').length).toBeGreaterThan(0);
});
test('OJ-02 regression: unknown XSD/OWL ontology uses all-source vocabulary browsing',async()=>{
 window.location.hash='#/ontology?target=qif-id';state.rows=[{ontology_id:'qif-id',prefix:'qif',label:'QIF',file_type:'xsd'}];
 state.taxonomy.mockResolvedValue({data:{nodes:[],edges:[]}});state.dictionary.mockResolvedValue({data:{entities:{Part:{iri:'urn:part'}},relationships:{},properties:{}}});state.mappings.mockResolvedValue({data:{mappings:{}}});
 render(<OntologyMapper/>);await screen.findByRole('option',{name:/QIF/});
 fireEvent.click(screen.getByRole('tab',{name:'1. Mapping Vocabulary'}));
 await waitFor(()=>expect(state.mappings).toHaveBeenCalledWith('qif-id','all',expect.anything()));
});
