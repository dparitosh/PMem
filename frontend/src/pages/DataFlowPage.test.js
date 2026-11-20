import { setCredentialProfile, getCredentialProfile } from '../services/serviceAuth';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import DataFlowPage from './DataFlowPage';

beforeEach(()=>{window.history.replaceState(null,'','#/data-flow');});

vi.mock('../services/apiClient', () => ({
  metadataRegistryAPI:{list:vi.fn().mockResolvedValue({data:{assets:[{asset_id:'model',version:'1',name:'Engineering model',lifecycle_status:'approved'}]}})},
  dataPipelineAPI: {
    submitPublicationReview:vi.fn().mockResolvedValue({data:{run_id:'review-input'}}),
    semanticResult: vi.fn().mockImplementation(id=>Promise.resolve({data:{run_id:id,rows:[],dimensions:[]}})),
    speedReviews: vi.fn().mockResolvedValue({data:{reconciliations:[],next_offset:null}}),
    health: vi.fn().mockResolvedValue({ data: { status: 'configured' } }),
    telemetry: vi.fn().mockResolvedValue({ data: {
      durable_job_telemetry: { runs: 100, records_accepted: 0, records_rejected: 0, limit: 100 },
    } }),
    runs: vi.fn().mockResolvedValue({ data: { runs: [{ run_id: 'one', job_id: 'test',
      output_manifest: { counts: { accepted_records: 987 } } }] } }),
    definitions: vi.fn().mockResolvedValue({ data: { definitions: [] } }),
    approveDefinition: vi.fn().mockResolvedValue({ data: { lifecycle_state: 'approved' } }),
    disableDefinition: vi.fn().mockResolvedValue({ data: { lifecycle_state: 'disabled' } }),
    scheduleDefinition: vi.fn().mockResolvedValue({ data: { schedule: { interval_seconds: 300 } } }),
    disableSchedule: vi.fn().mockResolvedValue({ data: {} }),
    executionIdentity: vi.fn().mockResolvedValue({data:{actor:'pipeline-steward'}}),
    replay: vi.fn().mockResolvedValue({ data: { status: 'queued', run_manifest: { run_id: 'replayed', status: 'queued', replay_of: 'one' } } }),
    getRun: vi.fn().mockImplementation(id => Promise.resolve({ data: { run_id: id, status: 'queued', replay_of: 'one' } })),
  },
}));

test('shows configuration status and explicitly bounded telemetry totals', async () => {
  render(<DataFlowPage />);
  expect(await screen.findByText('configured')).toBeInTheDocument();
  expect(screen.getByText('Accepted records').parentElement).toHaveTextContent('Accepted records0');
  expect(screen.getByText(/not lifetime history/)).toBeInTheDocument();
});

test('failed run reads remain explicit without duplicate quality controls',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');dataPipelineAPI.runs.mockRejectedValueOnce(new Error('Unavailable'));
 render(<DataFlowPage/>);await screen.findByText(/Some processing-job evidence is temporarily unavailable/);expect(screen.queryByRole('tab',{name:'Quality & evidence'})).toBeNull();expect(screen.getByRole('link',{name:'View data quality'})).toHaveAttribute('href','#/data-quality');
});


test('Run now reuses the retained input instead of submitting an empty payload', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  dataPipelineAPI.definitions.mockResolvedValueOnce({data:{definitions:[{job_id:'test',version:'1',lifecycle_state:'approved',enabled:true}]}});
  dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[{run_id:'retained-input',job_id:'test',job_version:'1',status:'completed'}]}});
  render(<DataFlowPage />);
  fireEvent.click(screen.getByRole('tab',{name:'Pipeline jobs'}));
  fireEvent.click(await screen.findByRole('button', {name:'Run now'}));
  fireEvent.click(await screen.findByRole('button',{name:'Confirm replay retained run'}));
  await waitFor(() => expect(dataPipelineAPI.replay).toHaveBeenCalledWith('retained-input', expect.any(Object)));
});

test('sends explicit in-memory approval data for a direct replay', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  dataPipelineAPI.runs.mockReset().mockResolvedValue({ data: { runs: [{ run_id: 'one', job_id: 'test', output_manifest: { counts: { accepted_records: 987 } } }] } });
  render(<DataFlowPage />);
  await screen.findByText('configured');

  setCredentialProfile('DATA_JOB_EXECUTION_TOKEN', 'direct-token');
  fireEvent.click(screen.getByRole('tab',{name:'Run monitor'}));
  const runRow = (await screen.findByRole('button', { name: 'test' })).closest('tr');
  fireEvent.click([...runRow.querySelectorAll('button')].find(button => button.textContent === 'Replay'));
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm replay retained run' }));
  await waitFor(() => expect(dataPipelineAPI.replay).toHaveBeenCalledWith('one', {
    approved_by: 'pipeline-steward',
    approval_token: 'direct-token',
    idempotency_key: expect.any(String),
  }));
  const receipt=await screen.findByRole('status',{name:'Last action result'});
  expect(receipt).toHaveTextContent('rerun queued');
  expect(receipt).not.toHaveTextContent('replayed');
  expect(window.location.hash).toContain('replayed');
  expect(screen.queryByLabelText('Replay execution API key')).toBeNull();
});




test('fetches a requested historical run absent from the recent list', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  window.location.hash = '#/data-flow/historical';
  render(<DataFlowPage />);
  await screen.findByText('historical');
  expect(dataPipelineAPI.getRun).toHaveBeenCalledWith('historical',expect.objectContaining({signal:expect.any(AbortSignal)}));
  window.location.hash = '';
});
test('does not select another run when a requested run is missing', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  dataPipelineAPI.getRun.mockRejectedValueOnce(new Error('Missing'));
  window.location.hash = '#/data-flow/missing';
  render(<DataFlowPage />);
  await screen.findByText(/Requested run is missing or inaccessible/);
  expect(screen.queryByText('Run ID')).not.toBeInTheDocument();
  window.location.hash = '';
});

test('cockpit separates pipeline configuration from runs and filters run status without executing a job',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.replay.mockClear();
 render(<DataFlowPage/>);
 await screen.findByText('configured');
 expect(screen.queryByRole('heading',{name:'Data-job definitions'})).toBeNull();
 fireEvent.change(screen.getByLabelText('Run status'),{target:{value:'failed'}});
 expect(screen.getByText('No durable job runs match the current filter.')).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'Pipeline jobs'}));
 expect(screen.getByRole('heading',{name:'Data-job definitions'})).toBeVisible();
 expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
});

test('pipeline jobs explain missing inputs and prevent empty run and schedule attempts',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.definitions.mockResolvedValueOnce({data:{definitions:[{job_id:'new',version:'1',lifecycle_state:'approved',enabled:true}]}});
 render(<DataFlowPage/>);
 await screen.findByText('configured');
 fireEvent.click(screen.getByRole('tab',{name:'Pipeline jobs'}));
 expect(await screen.findByRole('button',{name:'Run now'})).toBeDisabled();
 expect(screen.queryByRole('button',{name:'Schedule',exact:true})).toBeNull();
 expect(screen.getByRole('link',{name:'Review workflow change'})).toHaveAttribute('href',expect.stringContaining('record_source=definitions'));
 expect(screen.getByRole('link',{name:'Import source data first'})).toHaveAttribute('href','#/import');
});

test('retired quality and approval deep links keep run navigation without offering governance mutations',async()=>{
 window.history.replaceState(null,'','#/data-flow?view=settings');render(<DataFlowPage/>);await screen.findByText('configured');expect(screen.getByRole('tab',{name:'Run monitor'})).toHaveAttribute('aria-selected','true');expect(screen.queryByRole('tab',{name:'Approval & publication'})).toBeNull();expect(screen.getByRole('link',{name:'Open Change Control'})).toHaveAttribute('href','#/change-control');
});


test('run-id search retains published receipt and removes repeat publication action',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[{run_id:'exact-run',job_id:'semantic-source-validation',status:'completed',job_type:'validate-semantic-batch',output_manifest:{publication:{status:'published',publication_id:'receipt',ontology_id:'ceim-document'}}}]}});
 render(<DataFlowPage/>);
 expect(await screen.findByText('Published · receipt retained')).toBeInTheDocument();
 fireEvent.change(screen.getByRole('textbox',{name:'Find a run'}),{target:{value:'exact-run'}});
 expect(screen.getByText('Published · receipt retained')).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Request publication review',exact:true})).toBeNull();
});

test('disabled Spark is separate from the responding pipeline API',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.health.mockResolvedValueOnce({data:{status:'disabled',worker_count:1}});
 render(<DataFlowPage/>);
 await screen.findByText('responding');
 expect(screen.getByText('Pipeline API').parentElement).toHaveTextContent('responding');
 expect(screen.getByText('Spark engine').parentElement).toHaveTextContent('disabled');
});

test('query-style run links select the requested run instead of the latest record',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');window.history.replaceState(null,'','#/data-flow?run_id=requested-query');
 render(<DataFlowPage/>);await screen.findByText('Technical run references');fireEvent.click(screen.getByText('Technical run references'));expect(await screen.findByText('requested-query')).toBeVisible();
 expect(dataPipelineAPI.getRun).toHaveBeenCalledWith('requested-query',expect.objectContaining({signal:expect.any(AbortSignal)}));window.history.replaceState(null,'','#/');
});

test('renders only 25 loaded run rows per page while retaining all loaded evidence',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:Array.from({length:100},(_,i)=>({run_id:`run-${i}`,job_id:`job-${i}`,status:'completed'}))}});
 render(<DataFlowPage/>);await screen.findByRole('button',{name:'job-0',exact:true});
 expect(screen.queryByRole('button',{name:'job-25',exact:true})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Next runs'}));expect(screen.getByRole('button',{name:'job-25',exact:true})).toBeVisible();
 expect(screen.queryByRole('button',{name:'job-0',exact:true})).not.toBeInTheDocument();
});


test('changing a run deep link clears old evidence while the new response is pending',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 window.location.hash='#/data-flow';render(<DataFlowPage/>);
 await screen.findByText('Run ID');
 let resolve;dataPipelineAPI.runs.mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
 window.location.hash='#/data-flow?run_id=another';fireEvent(window,new Event('hashchange'));
 await waitFor(()=>expect(screen.queryByText('Run ID')).not.toBeInTheDocument());
 resolve({data:{runs:[{run_id:'another',status:'completed'}]}});
 await screen.findByText('another');window.location.hash='';
});


test('rejects execution preflight once and blocks repeated replay until revalidation',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.replay.mockClear();dataPipelineAPI.executionIdentity.mockClear();
 dataPipelineAPI.executionIdentity.mockRejectedValueOnce({response:{status:403,data:{detail:'Browser session scope is unavailable or credentials changed'}}});
 render(<DataFlowPage/>);await screen.findByText('configured');
 const replay=await screen.findByRole('button',{name:'Replay',exact:true});fireEvent.click(replay);
 fireEvent.click(screen.getByRole('button',{name:'Confirm replay retained run'}));
 await screen.findByText(/Replay access was rejected/);
 expect(replay).toBeDisabled();fireEvent.click(replay);
 expect(dataPipelineAPI.executionIdentity).toHaveBeenCalledTimes(1);
 expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
 fireEvent(window,new Event('depo:access-verified'));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Replay',exact:true})).toBeEnabled());
});

test('connection change during execution preflight never submits replay',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');dataPipelineAPI.replay.mockClear();let finish;
 dataPipelineAPI.executionIdentity.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 render(<DataFlowPage/>);await screen.findByText('configured');
 fireEvent.click(await screen.findByRole('button',{name:'Replay',exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'Confirm replay retained run'}));
 await waitFor(()=>expect(finish).toBeTypeOf('function'));
 fireEvent(window,new Event('depo:session-replaced'));finish({data:{actor:'old-connection'}});
 await waitFor(()=>expect(screen.queryByText('Replaying…')).toBeNull());
 expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
});

test('invalid execution identity fails before the write request',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');dataPipelineAPI.replay.mockClear();
 dataPipelineAPI.executionIdentity.mockResolvedValueOnce({data:{}});
 render(<DataFlowPage/>);await screen.findByText('configured');fireEvent.click(await screen.findByRole('button',{name:'Replay',exact:true}));
 fireEvent.click(screen.getByRole('button',{name:'Confirm replay retained run'}));
 await screen.findByText(/Execution identity could not be verified/);expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
});


test('queued and running runs cannot submit another replay', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  dataPipelineAPI.replay.mockClear();
  dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[
    {run_id:'queued-input',job_id:'queued-job',status:'queued'},
    {run_id:'running-input',job_id:'running-job',status:'running'}]}});
  render(<DataFlowPage />);
  await screen.findByText('queued-job');
  for(const button of screen.getAllByRole('button',{name:'Replay',exact:true})) {
    expect(button).toBeDisabled(); fireEvent.click(button);
  }
  expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
});


test('workspace is deep linked and follows browser history without replaying', async () => {
  window.history.replaceState(null,'','#/data-flow?view=quality&run_id=historical');
  render(<DataFlowPage />);
  expect(screen.getByRole('tab',{name:'Run monitor'})).toHaveAttribute('aria-selected','true');
  fireEvent.click(screen.getByRole('tab',{name:'Pipeline jobs'}));
  expect(window.location.hash).toContain('view=pipelines');
  expect(window.location.hash).toContain('run_id=historical');
  window.history.replaceState(null,'','#/data-flow?view=events');
  fireEvent(window,new PopStateEvent('popstate'));
  expect(screen.getByRole('tab',{name:'Event reviews'})).toHaveAttribute('aria-selected','true');
});

test('leaving Data Flow aborts all owned read requests', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  dataPipelineAPI.health.mockImplementationOnce(()=>new Promise(()=>{}));
  const {unmount}=render(<DataFlowPage />);
  const options=dataPipelineAPI.health.mock.calls.at(-1)[0];
  expect(options.signal.aborted).toBe(false);
  unmount();expect(options.signal.aborted).toBe(true);
});




test('legacy definitions view opens pipeline jobs without losing deep-link parameters',async()=>{
 window.history.replaceState(null,'','#/data-flow?view=definitions&job_id=keep-job');
 render(<DataFlowPage/>);
 expect(screen.getByRole('tab',{name:'Pipeline jobs'})).toHaveAttribute('aria-selected','true');
 expect(await screen.findByRole('heading',{name:'Data-job definitions'})).toBeVisible();
 expect(window.location.hash).toContain('job_id=keep-job');
});

test('completed preparation without validation counts is not presented as zero accepted and rejected',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[{run_id:'unassessed',job_id:'snapshot-job',job_type:'graph-source-snapshot',status:'completed',output_manifest:{counts:{records:9}}}]}});
 render(<DataFlowPage/>);
 expect(await screen.findByText('Validation not assessed')).toBeVisible();
 expect(screen.queryByText('0 accepted · 0 rejected')).toBeNull();
 expect(screen.getByText('Accepted records').parentElement).toHaveTextContent('—');
 expect(screen.queryByRole('tab',{name:'Quality & evidence'})).toBeNull();
 expect(screen.getByRole('link',{name:'View data quality'})).toBeVisible();
});

test('explicit validation zeros remain evidence rather than unknown',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[{run_id:'zero-assessment',job_id:'zero-job',status:'completed',output_manifest:{counts:{accepted_records:0,rejected_records:0}}}]}});
 render(<DataFlowPage/>);
 expect(await screen.findByText('0 accepted · 0 rejected')).toBeVisible();
 expect(screen.queryByText('Validation not assessed')).toBeNull();
});

test('partial validation evidence does not invent the missing rejected count',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[{run_id:'partial-assessment',job_id:'partial-job',status:'completed',output_manifest:{counts:{accepted_records:4}}}]}});
 render(<DataFlowPage/>);
 expect(await screen.findByText('4 accepted · — rejected')).toBeVisible();
 expect(screen.getByText('Rejected records').parentElement).toHaveTextContent('—');
});




test('a retained run request links to central review instead of offering a publication write',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[{run_id:'review-run',job_id:'semantic-source-validation',status:'completed',job_type:'validate-semantic-batch',change_request:{state:'submitted',revision:1},output_manifest:{partition_artifacts:{accepted:'sha256:partition'}}}]}});
 render(<DataFlowPage/>);
 const link=await screen.findByRole('link',{name:'Open change request'});
 expect(link).toHaveAttribute('href','#/change-control?source=pipeline&view=requests&record_source=pipeline&record=review-run');
 expect(screen.queryByRole('button',{name:'Request publication review',exact:true})).toBeNull();
});

test('an eligible run hands proposal creation to Change Control without issuing a write',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');dataPipelineAPI.submitPublicationReview.mockClear();dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[{run_id:'review-input',job_id:'semantic-source-validation',status:'completed',job_type:'validate-semantic-batch',output_manifest:{partition_artifacts:{accepted:'sha256:partition'}}}]}});
 render(<DataFlowPage/>);const link=await screen.findByRole('link',{name:'Request change in Change Control'});expect(link).toHaveAttribute('href','#/change-control?source=pipeline&view=workflows&record_source=pipeline&record=review-input');expect(dataPipelineAPI.submitPublicationReview).not.toHaveBeenCalled();
});


test('central definition review links retain exact version and friendly name',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.definitions.mockResolvedValueOnce({data:{definitions:[{job_id:'validate-source',name:'Validate engineering source',workflow_number:'WF-2026-000004',version:'1.0.0',lifecycle_state:'approved',enabled:true}]}});
 window.history.replaceState(null,'','#/data-flow?view=pipelines&definition_id=validate-source&definition_version=1.0.0');
 render(<DataFlowPage/>);
 await screen.findByText('Selected workflow: Validate engineering source · Version: 1.0.0');
 expect(screen.getByText(/WF-2026-000004/)).toBeInTheDocument();
});


test('legacy assistance links resolve to Run monitor without a duplicate agent form',async()=>{
 window.history.replaceState(null,'','#/data-flow?view=agent&run_id=one');render(<DataFlowPage/>);
 expect(screen.getByRole('tab',{name:'Run monitor'})).toHaveAttribute('aria-selected','true');
 expect(screen.queryByRole('tab',{name:'Agent assistance'})).toBeNull();expect(screen.queryByRole('textbox',{name:'Recommendation task'})).toBeNull();
 expect(await screen.findByRole('link',{name:'Open Agent Control'})).toHaveAttribute('href','#/admin?view=agents&source=data-flow&run_id=one');
});


test('shows retained CR and CO references directly in the run register',async()=>{
 const {dataPipelineAPI}=await import('../services/apiClient');
 dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[{run_id:'linked',job_id:'source-validation',status:'completed',change_request:{request_number:'CR-2026-000021',order:{order_number:'CO-2026-000031'}}}]}});
 render(<DataFlowPage/>);
 expect(await screen.findByText('CR-2026-000021')).toBeInTheDocument();
 expect(screen.getByText('CO-2026-000031')).toBeInTheDocument();
 expect(screen.getByRole('columnheader',{name:'CR / CO'})).toBeInTheDocument();
});
