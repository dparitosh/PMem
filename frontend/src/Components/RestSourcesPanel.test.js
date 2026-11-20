import React from 'react';
import { vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import RestSourcesPanel from './RestSourcesPanel';
import { dataPipelineAPI as api } from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{restSources:vi.fn(),definitions:vi.fn(),registerRestSource:vi.fn(),previewRestSource:vi.fn(),createDefinition:vi.fn(),runDefinition:vi.fn(),restSubmission:vi.fn(),getRun:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'session-token'}));
beforeEach(()=>{
  localStorage.clear();
  vi.clearAllMocks();
  api.restSources.mockResolvedValue({data:{sources:[{source_id:'parts-api',name:'PLM parts'}]}});
  api.definitions.mockResolvedValue({data:{definitions:[{job_id:'fetch',version:'1.0.0',name:'Fetch parts',job_type:'rest-source-ingest',lifecycle_state:'approved',enabled:true},{job_id:'draft',version:'1.0.0',name:'Unapproved',job_type:'rest-source-ingest',lifecycle_state:'draft',enabled:true}]}});
});
test('preview and worker submission use selected source and approved definition',async()=>{
  api.previewRestSource.mockResolvedValue({data:{record_count:1,records:[{name:'Part A'}]}});
  api.runDefinition.mockResolvedValue({data:{run_manifest:{run_id:'run-rest',status:'queued'}}});
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));
  await screen.findByRole('button',{name:'Select PLM parts'});
  await waitFor(()=>expect(screen.getByText('Refresh sources and jobs')).not.toBeDisabled());
  expect(screen.queryByText('Unapproved')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Select PLM parts'}));
  fireEvent.click(screen.getByText('Test connection and preview'));
  await screen.findByText('Part A');
  expect(api.previewRestSource).toHaveBeenCalledWith('parts-api','session-token');
  fireEvent.change(screen.getByLabelText('Approved acquisition job'),{target:{value:'fetch@1.0.0'}});
  fireEvent.click(screen.getByText('Fetch records with worker'));
  await screen.findByText(/Run run-rest:/);
  expect(api.runDefinition).toHaveBeenCalledWith('fetch','1.0.0',expect.objectContaining({source_id:'parts-api',idempotency_key:expect.any(String)}),expect.objectContaining({approval_token:'session-token'}));
});
test('late responses after session invalidation cannot restore sources',async()=>{
  let finish;
  api.restSources.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));
  act(()=>window.dispatchEvent(new Event('depo:session-expired')));
  await act(async()=>finish({data:{sources:[{source_id:'old',name:'Old session source'}]}}));
  expect(screen.queryByText('Old session source')).toBeNull();
  expect(screen.getByRole('alert')).toHaveTextContent('Access changed');
});
test('rapid submission only queues one run',async()=>{
  let finish;
  api.runDefinition.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));
  await screen.findByRole('button',{name:'Select PLM parts'});
  await waitFor(()=>expect(screen.getByText('Refresh sources and jobs')).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button',{name:'Select PLM parts'}));
  fireEvent.change(screen.getByLabelText('Approved acquisition job'),{target:{value:'fetch@1.0.0'}});
  const button=screen.getByText('Fetch records with worker');
  fireEvent.click(button);fireEvent.click(button);
  expect(api.runDefinition).toHaveBeenCalledTimes(1);
  await act(async()=>finish({data:{run_manifest:{run_id:'one',status:'queued'}}}));
});

test('source paging requests a bounded next page and removes stale selection',async()=>{
  api.restSources.mockResolvedValueOnce({data:{sources:[{source_id:'first',name:'First'}],total:51,next_offset:50}})
    .mockResolvedValueOnce({data:{sources:[{source_id:'last',name:'Last'}],total:51,next_offset:null}});
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));await screen.findByRole('button',{name:'Select First'});
  await waitFor(()=>expect(screen.getByText('Refresh sources and jobs')).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button',{name:'Select First'}));
  fireEvent.click(screen.getByText('Next sources'));await screen.findByRole('button',{name:'Select Last'});
  expect(api.restSources).toHaveBeenLastCalledWith({params:{limit:50,offset:50}});
  expect(screen.getByText('Test connection and preview')).toBeDisabled();
});

test('source preview does not wait for an unresolved job catalog',async()=>{
  let finish;
  api.definitions.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  api.previewRestSource.mockResolvedValue({data:{record_count:1,records:[{name:'Independent Part'}]}});
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));await screen.findByRole('button',{name:'Select PLM parts'});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Select PLM parts'})).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button',{name:'Select PLM parts'}));
  fireEvent.click(screen.getByText('Test connection and preview'));await screen.findByText('Independent Part');
  await act(async()=>finish({data:{definitions:[]}}));
});

test('mismatched pending receipt does not trigger recovery execution',async()=>{
 const retained={key:'saved-key',source:'parts-api',jobId:'fetch',version:'1.0.0'};
 localStorage.setItem('depo:rest-source-submission:v1',JSON.stringify(retained));
 api.restSubmission.mockResolvedValue({data:{status:'pending_enqueue',submission_id:'other-key'}});
 render(<RestSourcesPanel/>);
 fireEvent.click(screen.getByText('Refresh retained submission'));
 expect(await screen.findByRole('alert')).toHaveTextContent('does not match');
 expect(api.runDefinition).not.toHaveBeenCalled();
 expect(JSON.parse(localStorage.getItem('depo:rest-source-submission:v1'))).toEqual(retained);
});

test('late REST status response cannot replace another tab submission',async()=>{
 let finish;
 const old={key:'old',source:'parts-api',jobId:'fetch',version:'1.0.0',runId:'old-run'};
 localStorage.setItem('depo:rest-source-submission:v1',JSON.stringify(old));
 api.getRun.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 render(<RestSourcesPanel/>);fireEvent.click(screen.getByText('Refresh retained submission'));
 const newer={...old,key:'new',runId:'new-run'};
 localStorage.setItem('depo:rest-source-submission:v1',JSON.stringify(newer));
 await act(async()=>finish({data:{run_id:'old-run',status:'completed'}}));
 expect(await screen.findByRole('alert')).toHaveTextContent('another tab');
 expect(JSON.parse(localStorage.getItem('depo:rest-source-submission:v1'))).toEqual(newer);
});

test('pending status inspection is read-only and explicit recovery reuses the saved key',async()=>{
 const retained={key:'saved-key',source:'parts-api',jobId:'fetch',version:'1.0.0'};
 localStorage.setItem('depo:rest-source-submission:v1',JSON.stringify(retained));
 api.restSubmission.mockResolvedValue({data:{status:'pending_enqueue',submission_id:'saved-key'}});
 api.runDefinition.mockResolvedValue({data:{run_manifest:{run_id:'recovered',status:'queued'}}});
 render(<RestSourcesPanel/>);fireEvent.click(screen.getByText('Refresh retained submission'));
 await screen.findByText(/No fetch was submitted by this status check/);
 expect(api.runDefinition).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('Recover same submission'));
 await screen.findByText(/Run recovered: queued/);
 expect(api.runDefinition).toHaveBeenCalledWith('fetch','1.0.0',{source_id:'parts-api',idempotency_key:'saved-key'},expect.any(Object));
});

test('missing receipt on status refresh does not replay acquisition',async()=>{
 const retained={key:'missing-key',source:'parts-api',jobId:'fetch',version:'1.0.0'};
 localStorage.setItem('depo:rest-source-submission:v1',JSON.stringify(retained));
 api.restSubmission.mockRejectedValue({response:{status:404,data:{detail:'Submission not retained'}}});
 render(<RestSourcesPanel/>);fireEvent.click(screen.getByText('Refresh retained submission'));
 await screen.findByRole('alert');
 expect(api.runDefinition).not.toHaveBeenCalled();
 expect(JSON.parse(localStorage.getItem('depo:rest-source-submission:v1'))).toEqual(retained);
});

test('unloaded and failed reads do not display zero records or offer job creation',async()=>{
 api.restSources.mockRejectedValue(new Error('Sources offline'));
 api.definitions.mockRejectedValue(new Error('Jobs offline'));
 render(<RestSourcesPanel/>);
 expect(screen.getByText('Loading sources…')).toBeVisible();
 expect(screen.queryByText(/0 sources/)).not.toBeInTheDocument();
 expect(screen.queryByText('Create acquisition job draft')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Refresh sources and jobs'));
 await screen.findByText('Source count unavailable');
 expect(screen.getByText(/Approved acquisition jobs are unavailable/)).toBeVisible();
 expect(screen.queryByText('Create acquisition job draft')).not.toBeInTheDocument();
 expect(screen.getByText('Fetch records with worker')).toBeDisabled();
});


test('ten registered APIs are visible, searchable and selectable without execution',async()=>{
 const sources=Array.from({length:10},(_,i)=>({source_id:`api-${i+1}`,name:`Business API ${i+1}`,endpoint:`https://api.example.com/source-${i+1}`,credential_ref:'DEPO_REST_SECRET_TEST'}));
 api.restSources.mockResolvedValue({data:{sources,total:10,next_offset:null}});
 render(<RestSourcesPanel/>);fireEvent.click(screen.getByText('Refresh sources and jobs'));
 await screen.findByRole('table',{name:'Registered REST APIs'});
 expect(screen.getAllByRole('button',{name:/^Select Business API/})).toHaveLength(10);
 expect(screen.getByText(/10 shown on this page/)).toBeVisible();
 fireEvent.change(screen.getByRole('searchbox',{name:'Find registered APIs'}),{target:{value:'source-7'}});
 expect(screen.getAllByRole('button',{name:/^Select Business API/})).toHaveLength(1);
 fireEvent.click(screen.getByRole('button',{name:'Select Business API 7'}));
 expect(screen.getByRole('button',{name:'Select Business API 7'})).toHaveAttribute('aria-pressed','true');
 expect(screen.getByText('Test connection and preview')).toBeEnabled();
 expect(api.runDefinition).not.toHaveBeenCalled();
});

test.each([null,{source_id:'bad',name:{label:'bad'}},{source_id:'bad',name:'Bad',endpoint:{url:'bad'}}])('invalid inventory row is handled without rendering failure: %j',async row=>{
 api.restSources.mockResolvedValue({data:{sources:[row],total:1}});
 render(<RestSourcesPanel/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('invalid records');
 expect(screen.getByText('Source count unavailable')).toBeVisible();
 expect(screen.getByText('Test connection and preview')).toBeDisabled();
});

test('invalid preview cannot claim connection success',async()=>{
 api.previewRestSource.mockResolvedValue({data:{record_count:1,records:[null]}});
 render(<RestSourcesPanel/>);await screen.findByRole('button',{name:'Select PLM parts'});
 fireEvent.click(screen.getByRole('button',{name:'Select PLM parts'}));
 fireEvent.click(screen.getByText('Test connection and preview'));
 expect(await screen.findByRole('alert')).toHaveTextContent('Preview returned invalid');
 expect(screen.queryByText(/Connection succeeded/)).toBeNull();
});

function registrationForm(){
 fireEvent.change(screen.getByLabelText('Source ID'),{target:{value:'new-api'}});
 fireEvent.change(screen.getByLabelText('Source name'),{target:{value:'New API'}});
 fireEvent.change(screen.getByLabelText('HTTP(S) endpoint'),{target:{value:'https://example.com/parts'}});
 fireEvent.click(screen.getByText('Register source'));
}

test('registration freezes fields and refreshes authoritative total after failed inventory',async()=>{
 api.restSources.mockRejectedValueOnce(new Error('Offline'));
 let finish;api.registerRestSource.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
 render(<RestSourcesPanel/>);await screen.findByText('Source count unavailable');
 registrationForm();
 expect(screen.getByLabelText('Source name')).toBeDisabled();
 expect(screen.getByLabelText('Authentication header')).toBeDisabled();
 api.restSources.mockResolvedValue({data:{sources:[{source_id:'new-api',name:'New API'}],total:42}});
 await act(async()=>finish({data:{source_id:'new-api',name:'New API'}}));
 await screen.findByText(/42 registered API/);
 expect(screen.getByRole('region',{name:'Selected source details'})).toHaveTextContent('New API');
 fireEvent.click(screen.getByRole('button',{name:'Add source'}));
 expect(screen.getByLabelText('Source name')).toHaveValue('');
});

test('mismatched registration receipt preserves draft and inventory',async()=>{
 api.registerRestSource.mockResolvedValue({data:{source_id:'other-api',name:'Other API'}});
 render(<RestSourcesPanel/>);await screen.findByRole('button',{name:'Select PLM parts'});
 registrationForm();
 expect(await screen.findByRole('alert')).toHaveTextContent('registration was not confirmed');
 expect(screen.getByLabelText('Source ID')).toHaveValue('new-api');
 expect(screen.queryByRole('option',{name:'Other API'})).toBeNull();
});

test('registration fields match backend identifier and secret reference limits',()=>{
 render(<RestSourcesPanel/>);
 expect(screen.getByLabelText('Source ID')).toHaveAttribute('maxlength','63');
 expect(screen.getByLabelText('Server secret reference (optional)')).toHaveAttribute('maxlength','81');
 expect(screen.getByLabelText('Server secret reference (optional)')).toHaveAttribute('pattern','DEPO_REST_SECRET_[A-Z0-9_]{1,64}');
});


test('OpenAPI import prepares a draft and saves its contract through the existing registration API',async()=>{
 const document={openapi:'3.0.3',info:{title:'Engineering API'},servers:[{url:'https://api.example.com/v1'}],paths:{'/parts':{get:{summary:'Released parts'}}}};
 api.restSources.mockResolvedValue({data:{sources:[],total:0}});
 api.registerRestSource.mockImplementation(payload=>Promise.resolve({data:{...payload,source_number:'DS-2026-000100'}}));
 render(<RestSourcesPanel/>);await screen.findByText(/No REST APIs registered yet/);
 const file=new File([JSON.stringify(document)],'engineering.json',{type:'application/json'});file.text=()=>Promise.resolve(JSON.stringify(document));
 fireEvent.change(screen.getByLabelText('Import OpenAPI JSON'),{target:{files:[file]}});
 await screen.findByLabelText('OpenAPI operation');expect(screen.getByText('Register source')).toBeDisabled();fireEvent.change(screen.getByLabelText('OpenAPI operation'),{target:{value:'/parts:0'}});
 expect(screen.getByLabelText('Source name')).toHaveValue('Released parts');expect(screen.getByLabelText('HTTP(S) endpoint')).toHaveValue('https://api.example.com/v1/parts');
 expect(api.registerRestSource).not.toHaveBeenCalled();fireEvent.click(screen.getByText('Register source'));
 await waitFor(()=>expect(api.registerRestSource).toHaveBeenCalledOnce());
 expect(api.registerRestSource.mock.calls[0][0]).toMatchObject({openapi_document:document,openapi_path:'/parts',endpoint:'https://api.example.com/v1/parts'});
});
test('session replacement clears source-entry drafts and imported operation state',async()=>{
 render(<RestSourcesPanel/>);fireEvent.change(screen.getByLabelText('Source name'),{target:{value:'Old user draft'}});
 act(()=>window.dispatchEvent(new Event('depo:session-replaced')));expect(screen.getByLabelText('Source name')).toHaveValue('');
});


test('records path accepts dot-separated keys instead of requiring literal backslashes',()=>{
 render(<RestSourcesPanel/>);const input=screen.getByLabelText('Records path (optional)');
 expect(new RegExp('^(?:'+input.getAttribute('pattern')+')$').test('data.items')).toBe(true);
});


test('registered metadata awaiting host setup cannot be previewed or executed',async()=>{
 api.restSources.mockResolvedValue({data:{sources:[{source_id:'pending-api',name:'Pending API',endpoint:'https://api.example.com/parts',connection_ready:false}],total:1}});
 render(<RestSourcesPanel/>);fireEvent.click(await screen.findByRole('button',{name:'Select Pending API'}));
 expect(screen.getByText('Host setup needed')).toBeVisible();expect(screen.getByText(/Source saved. Ask the administrator/)).toBeVisible();
 expect(screen.getByText('Test connection and preview')).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Approved acquisition job'),{target:{value:'fetch@1.0.0'}});
 expect(screen.getByText('Fetch records with worker')).toBeDisabled();expect(api.previewRestSource).not.toHaveBeenCalled();
});


test('identifier patterns compile in modern browser Unicode-set mode',()=>{
 render(<RestSourcesPanel/>);
 expect(new RegExp(screen.getByLabelText('Source ID').getAttribute('pattern'),'v').test('engineering-parts')).toBe(true);
 expect(new RegExp(screen.getByLabelText('Records path (optional)').getAttribute('pattern'),'v').test('data.part-items')).toBe(true);
});
