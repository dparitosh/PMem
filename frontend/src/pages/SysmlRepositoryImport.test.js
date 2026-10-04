import { setCredentialProfile, getCredentialProfile } from '../services/serviceAuth';
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import SysmlRepositoryImport from './SysmlRepositoryImport';
import { apiClient } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
const ready = { enabled: true, configured: true, project_configured: true, commit_configured: true, project_id: 'project', commit_id: 'commit' };
beforeEach(() => { apiClient.get.mockReset(); apiClient.post.mockReset(); apiClient.get.mockResolvedValue({ data: ready }); });
async function configure() {
  render(<SysmlRepositoryImport />);
  fireEvent.click(screen.getByRole('button', { name: 'Check repository configuration' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Import configured commit' })).toBeEnabled());
}
test('executes an authorized import and displays the durable run', async () => {
  apiClient.post.mockResolvedValue({ data: { run_manifest: { run_id: 'run-1', status: 'completed' } } });
  await configure();
  setCredentialProfile('DATA_JOB_EXECUTION_TOKEN', 'execution-key');
  fireEvent.click(screen.getByRole('button', { name: 'Import configured commit' }));
  await screen.findByText(/run-1/);
  expect(apiClient.post.mock.calls[0][2].headers.Authorization).toBe('Bearer execution-key');
  expect(screen.queryByLabelText(/Execution key/)).toBeNull();
  expect(screen.getByRole('link', { name: /Open Data Flow/ })).toHaveAttribute('href', '#/data-flow/run-1');
});
test('failed configuration refresh disables import instead of retaining stale readiness', async () => {
  await configure();
  apiClient.get.mockRejectedValueOnce(new Error('Offline'));
  fireEvent.click(screen.getByRole('button', { name: 'Check repository configuration' }));
  await screen.findByRole('alert');
  expect(screen.getByRole('button', { name: 'Import configured commit' })).toBeDisabled();
});
test('a response without a run ID is shown as an error', async () => {
  apiClient.post.mockResolvedValue({ data: {} });
  await configure();
  setCredentialProfile('DATA_JOB_EXECUTION_TOKEN', 'execution-key');
  fireEvent.click(screen.getByRole('button', { name: 'Import configured commit' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('durable run ID');
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});
