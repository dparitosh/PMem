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
    replay: vi.fn().mockResolvedValue({ data: { status: 'queued' } }),
  },
}));

test('shows configuration status and explicitly bounded telemetry totals', async () => {
  render(<DataFlowPage />);
  expect(await screen.findByText('configured')).toBeInTheDocument();
  expect(screen.getByText('Accepted records').parentElement).toHaveTextContent('Accepted records0');
  expect(screen.getByText(/not lifetime history/)).toBeInTheDocument();
});

test('sends explicit in-memory approval data for a direct replay', async () => {
  const { dataPipelineAPI } = await import('../services/apiClient');
  render(<DataFlowPage />);
  await screen.findByText('configured');

  fireEvent.change(screen.getByLabelText('Replay approver'), { target: { value: 'pipeline-steward' } });
  fireEvent.change(screen.getByLabelText('Replay execution API key'), { target: { value: 'direct-token' } });
  fireEvent.click(screen.getByRole('button', { name: 'Replay' }));

  await waitFor(() => expect(dataPipelineAPI.replay).toHaveBeenCalledWith('one', {
    approved_by: 'pipeline-steward',
    approval_token: 'direct-token',
  }));
  expect(screen.getByLabelText('Replay execution API key')).toHaveValue('');
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
  fireEvent.change(screen.getByLabelText('Replay execution API key'), { target: { value: 'direct-token' } });
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

  await waitFor(() => expect(dataPipelineAPI.approveDefinition).toHaveBeenCalledWith('qif-quality', '1.0.0', {
    approved_by: 'pipeline-steward', approval_token: 'direct-token',
  }));
});
