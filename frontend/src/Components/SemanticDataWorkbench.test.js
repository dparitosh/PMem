vi.mock('./GraphSnapshotSource',()=>({default:()=>null}));
import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import SemanticDataWorkbench from './SemanticDataWorkbench';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{semanticSources:vi.fn(),semanticDatasets:vi.fn(),semanticSchema:vi.fn(),semanticChangeAssessment:vi.fn(),definitions:vi.fn(),executionIdentity:vi.fn(),runDefinition:vi.fn(),createDefinition:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'test-token'}));
beforeEach(()=>{
 vi.resetAllMocks();sessionStorage.clear();
 api.semanticSources.mockResolvedValue({data:{sources:[{source_id:'catalog:parts:1',artifact_id:'sha256:source',name:'Parts',version:'1'}]}});
 api.semanticDatasets.mockResolvedValue({data:{datasets:[]}});
 api.definitions.mockResolvedValue({data:{definitions:[{job_id:'prepare-parts',version:'1.0.0',name:'Prepare parts',job_type:'rdf-semantic-materialize',lifecycle_state:'approved',enabled:true}]}});
 api.executionIdentity.mockResolvedValue({data:{actor:'connected-user'}});
 api.runDefinition.mockResolvedValue({data:{run_manifest:{run_id:'retained-run'}}});
});
test('selects a registered source and submits its owned artifact to an approved worker',async()=>{
 render(<SemanticDataWorkbench/>);
 await screen.findByText('Connected requester: connected-user');
 fireEvent.change(screen.getByLabelText('Registered source'),{target:{value:'catalog:parts:1|sha256:source'}});
 const button=screen.getByRole('button',{name:'Prepare semantic records with worker'});
 fireEvent.click(button);fireEvent.click(button);
 await screen.findByText('Processing request retained. Inspect its result before creating another request.');
 expect(api.runDefinition).toHaveBeenCalledTimes(1);
 expect(api.runDefinition).toHaveBeenCalledWith('prepare-parts','1.0.0',{source_id:'catalog:parts:1',artifact_id:'sha256:source'},{approved_by:'connected-user',approval_token:'test-token'});
});
test('a failed catalog request is not presented as an empty catalog',async()=>{
 api.semanticSources.mockRejectedValue(new Error('offline'));render(<SemanticDataWorkbench/>);
 await screen.findByRole('alert');
 expect(screen.queryByText(/No retained RDF references/)).not.toBeInTheDocument();
});
test('unapproved processing is never executed',async()=>{
 api.definitions.mockResolvedValue({data:{definitions:[]}});render(<SemanticDataWorkbench/>);
 await screen.findByText('Connected requester: connected-user');
 expect(screen.getByRole('button',{name:'Prepare semantic records with worker'})).toBeDisabled();
 expect(api.runDefinition).not.toHaveBeenCalled();
});

test('missing processing definitions can be prepared as drafts without granting approval',async()=>{
 api.definitions.mockResolvedValue({data:{definitions:[]}});
 api.createDefinition.mockResolvedValue({data:{lifecycle_state:'draft'}});
 render(<SemanticDataWorkbench/>);
 const draftButton=await screen.findByRole('button',{name:'Prepare workflow draft for review'});
 await act(async()=>{fireEvent.click(draftButton);});
 await screen.findByText('Draft created. Review and approve this workflow in Data Flow before running it.');
 expect(api.createDefinition).toHaveBeenCalledWith(expect.objectContaining({job_type:'rdf-semantic-materialize',quality_profile:'semantic-core-v1'}),'test-token');
 expect(api.runDefinition).not.toHaveBeenCalled();
});

test('source review uses the selected dataset baseline without requiring an entity class',async()=>{
 const id='a'.repeat(64),baseline='b'.repeat(64);
 api.semanticDatasets.mockResolvedValue({data:{datasets:[{dataset_id:id,name:'Parts snapshot',counts:{entities:1},projection_version:'rdf-records-v1'}]}});
 api.semanticSchema.mockResolvedValue({data:{dataset:{dataset_id:id,configuration_id:baseline},classes:[],namespaces:[]}});
 api.semanticChangeAssessment.mockResolvedValue({data:{status:'refresh_required'}});
 api.definitions.mockResolvedValue({data:{definitions:[{job_id:'source-review',version:'1.0.0',name:'Assess source changes',job_type:'semantic-source-review',lifecycle_state:'approved',enabled:true}]}});
 render(<SemanticDataWorkbench/>);
 await screen.findByText('Connected requester: connected-user');
 fireEvent.change(screen.getByLabelText('Prepared semantic dataset'),{target:{value:id}});
 await screen.findByText(/Source change assessment: refresh required/);
 fireEvent.change(screen.getByLabelText('Analysis'),{target:{value:'source-review'}});
 fireEvent.click(screen.getByRole('button',{name:'Check source changes with worker'}));
 await screen.findByText('Processing request retained. Inspect its result before creating another request.');
 expect(api.runDefinition).toHaveBeenCalledWith('source-review','1.0.0',{dataset_id:id,configuration_id:baseline},expect.anything());
});

test('AUD-CFG-04 late rejection from the previous session must not overwrite current-session feedback',async()=>{
 let rejectSubmission;
 api.runDefinition.mockImplementation(()=>new Promise((resolve,reject)=>{rejectSubmission=reject;}));
 render(<SemanticDataWorkbench/>);
 await screen.findByText('Connected requester: connected-user');
 fireEvent.change(screen.getByLabelText('Registered source'),{target:{value:'catalog:parts:1|sha256:source'}});
 fireEvent.click(screen.getByRole('button',{name:'Prepare semantic records with worker'}));
 await act(async()=>{window.dispatchEvent(new Event('depo:session-replaced'));});
 await screen.findByText('Connected requester: connected-user');
 await act(async()=>{rejectSubmission({response:{status:403,data:{detail:'OLD SESSION REJECTION'}}});});
 expect(screen.queryByText('OLD SESSION REJECTION')).not.toBeInTheDocument();
});

test('late success after navigation retains a recoverable run receipt without updating an unmounted page',async()=>{
 let finishSubmission;
 api.runDefinition.mockImplementation(()=>new Promise(resolve=>{finishSubmission=resolve;}));
 const page=render(<SemanticDataWorkbench/>);
 await screen.findByText('Connected requester: connected-user');
 fireEvent.change(screen.getByLabelText('Registered source'),{target:{value:'catalog:parts:1|sha256:source'}});
 fireEvent.click(screen.getByRole('button',{name:'Prepare semantic records with worker'}));
 page.unmount();
 await act(async()=>{finishSubmission({data:{run_manifest:{run_id:'recover-after-navigation'}}});});
 expect(JSON.parse(sessionStorage.getItem('depo-semantic-data-task'))).toEqual(expect.objectContaining({run_id:'recover-after-navigation',previousConnection:true}));
});

 test('prepared snapshots show source versions and separate snapshot identities',async()=>{
 api.semanticDatasets.mockResolvedValue({data:{datasets:[
 {dataset_id:'a'.repeat(64),name:'Parts',source_version:{version:'1.0.0'},counts:{entities:2}},
 {dataset_id:'b'.repeat(64),name:'Parts',source_version:{version:'1.0.1'},counts:{entities:2}}
 ]}});
 render(<SemanticDataWorkbench/>);
 expect(await screen.findByRole('option',{name:/Parts · source 1.0.0 · snapshot aaaaaaaa/})).toBeInTheDocument();
 expect(screen.getByRole('option',{name:/Parts · source 1.0.1 · snapshot bbbbbbbb/})).toBeInTheDocument();
 });

test('namespace choices exclude unused defaults and duplicate aliases',async()=>{
 const id='c'.repeat(64);
 api.semanticDatasets.mockResolvedValue({data:{datasets:[{dataset_id:id,name:'Parts',counts:{entities:1}}]}});
 api.semanticSchema.mockResolvedValue({data:{dataset:{dataset_id:id},classes:[{iri:'urn:parts:Part',name:'Part',entities:1}],namespaces:[
 {namespace_uri:'urn:parts:',prefix:'parts'},{namespace_uri:'urn:parts:',prefix:'p'},
 {namespace_uri:'http://unused.example/',prefix:'unused'},{namespace_uri:'',prefix:''}]}});
 api.semanticChangeAssessment.mockResolvedValue({data:{status:'not_assessed'}});
 render(<SemanticDataWorkbench/>);
 await screen.findByText('Connected requester: connected-user');
 fireEvent.change(screen.getByLabelText('Prepared semantic dataset'),{target:{value:id}});
 const select=await screen.findByLabelText('Vocabulary / namespace');
 await waitFor(()=>expect(select.options.length).toBe(2));
 expect(select.options[1].value).toBe('urn:parts:');
 expect(select).not.toHaveTextContent('unused');
});
