import { setCredentialProfile, getCredentialProfile } from '../services/serviceAuth';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import DataFlowPage from './DataFlowPage';

vi.mock('../services/apiClient', () => ({
  dataPipelineAPI: {
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

test('marks quality unknown when the run evidence endpoint fails', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  dataPipelineAPI.runs.mockRejectedValueOnce(new Error('Run evidence unavailable'));
  render(<DataFlowPage />);
  expect(await screen.findByText(/Evidence is unavailable or stale/)).toBeInTheDocument();
  expect(screen.getByText('unknown')).toBeInTheDocument();
});

test('Run now reuses the retained input instead of submitting an empty payload', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  dataPipelineAPI.definitions.mockResolvedValueOnce({data:{definitions:[{job_id:'test',version:'1',lifecycle_state:'approved',enabled:true}]}});
  dataPipelineAPI.runs.mockResolvedValueOnce({data:{runs:[{run_id:'retained-input',job_id:'test',job_version:'1',status:'completed'}]}});
  render(<DataFlowPage />);
  fireEvent.click(await screen.findByRole('button', {name:'Run now'}));
  await waitFor(() => expect(dataPipelineAPI.replay).toHaveBeenCalledWith('retained-input', expect.any(Object)));
});

test('sends explicit in-memory approval data for a direct replay', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  render(<DataFlowPage />);
  await screen.findByText('configured');

  fireEvent.change(screen.getByLabelText('Replay approver'), { target: { value: 'pipeline-steward' } });
  setCredentialProfile('DATA_JOB_EXECUTION_TOKEN', 'direct-token');
  fireEvent.click(screen.getByRole('button', { name: 'Replay' }));

  await waitFor(() => expect(dataPipelineAPI.replay).toHaveBeenCalledWith('one', {
    approved_by: 'pipeline-steward',
    approval_token: 'direct-token',
  }));
  await screen.findByText('replayed');
  expect(screen.queryByLabelText('Replay execution API key')).toBeNull();
});

test('approves a registered data-job definition through the pipeline service', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  dataPipelineAPI.definitions.mockResolvedValueOnce({ data: { definitions: [{
    job_id: 'qif-quality', version: '1.0.0', name: 'QIF quality', owner: 'governance',
    lifecycle_state: 'draft', enabled: true, input_contract: 'records-v1', output_contract: 'quality-v1',
  }] } });
  render(<DataFlowPage />);
  await screen.findByText('QIF quality');
  fireEvent.change(screen.getByLabelText('Replay approver'), { target: { value: 'pipeline-steward' } });
  setCredentialProfile('DATA_JOB_APPROVAL_TOKEN', 'direct-token');
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

  await waitFor(() => expect(dataPipelineAPI.approveDefinition).toHaveBeenCalledWith('qif-quality', '1.0.0', {
    approved_by: 'pipeline-steward', approval_token: 'direct-token',
  }));
});

test('fetches a requested historical run absent from the recent list', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  window.location.hash = '#/data-flow/historical';
  render(<DataFlowPage />);
  await screen.findByText('historical');
  expect(dataPipelineAPI.getRun).toHaveBeenCalledWith('historical');
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
