import { render, screen } from '@testing-library/react';
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
  },
}));

test('shows configuration status and explicitly bounded telemetry totals', async () => {
  render(<DataFlowPage />);
  expect(await screen.findByText('configured')).toBeInTheDocument();
  expect(screen.getByText('Accepted records').parentElement).toHaveTextContent('Accepted records0');
  expect(screen.getByText(/not lifetime history/)).toBeInTheDocument();
});
