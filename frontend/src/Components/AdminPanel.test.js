import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import AdminPanel, { ConfirmationDialog } from './AdminPanel';
import { API_METHODS } from '../services/apiClient';
import { getCredentialProfile } from '../services/serviceAuth';
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: vi.fn(() => 'test-maintenance-key') }));
vi.mock('../services/apiClient', () => ({ API_METHODS: { admin: {
  health: vi.fn(async () => ({ data: { status: 'ok' } })),
  schemaStats: vi.fn(async () => ({ data: { stats: {} } })),
  clearCache: vi.fn(),
  clearImportWorkflows: vi.fn(),
  resetDatabase: vi.fn(),
  previewVanillaReset: vi.fn(),
  resetVanilla: vi.fn(),
}, agentic: { isConfigured: () => false } } }));
vi.mock('../contexts/OntologyContext', () => ({ useOntologies: () => ({ fetchOntologies: async () => {} }) }));

test('clearing import workflows requires confirmation and clears saved browser history after server success', async () => {
  API_METHODS.admin.clearImportWorkflows.mockResolvedValue({ data: { status: 'success', deleted_count: 3 } });
  window.localStorage.setItem('depo.import.jobs.v2', '{"files":[{"taskId":"old"}]}');
  render(<AdminPanel />);
  const button = screen.getByRole('button', { name: 'Clear Import Workflows' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  expect(API_METHODS.admin.clearImportWorkflows).not.toHaveBeenCalled();
  const confirm = screen.getByRole('button', { name: 'Clear workflows' });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Confirmation phrase'), { target: { value: 'CLEAR IMPORT WORKFLOWS' } });
  fireEvent.click(confirm);
  await screen.findByText(/Import workflows cleared: 3/);
  expect(window.localStorage.getItem('depo.import.jobs.v2')).toBeNull();
});

test('vanilla reset previews scope and cannot execute outside isolated maintenance', async () => {
  API_METHODS.admin.previewVanillaReset.mockResolvedValue({ data: { registry_records: { agentic_workflow_runs: 4 }, table_rows: {}, retained_files: { uploads: 2 }, can_execute: false, maintenance_instruction: 'Stop services and open isolated maintenance.' } });
  render(<AdminPanel />);
  const preview = screen.getByRole('button', { name: 'Preview vanilla reset' });
  await waitFor(() => expect(preview).toBeEnabled());
  fireEvent.click(preview);
  await screen.findByText('agentic_workflow_runs');
  expect(screen.getByRole('button', { name: 'Reset DEPO to vanilla state' })).toBeDisabled();
  expect(screen.getByText('Stop services and open isolated maintenance.')).toBeVisible();
  expect(API_METHODS.admin.resetVanilla).not.toHaveBeenCalled();
});

test('vanilla reset requires exact phrase and submits the preview identity once', async () => {
  sessionStorage.setItem('depo.browserSession.v1', 'existing-delegated-access');
  sessionStorage.setItem('bridge-workflow:old', 'obsolete-run');
  API_METHODS.admin.previewVanillaReset.mockResolvedValue({ data: { registry_records: {}, table_rows: {}, retained_files: {}, can_execute: true, preview_digest: 'preview-identity' } });
  API_METHODS.admin.resetVanilla.mockResolvedValue({ data: { status: 'completed', run_id: 'vanilla-test' } });
  render(<AdminPanel />);
  const preview = screen.getByRole('button', { name: 'Preview vanilla reset' });
  await waitFor(() => expect(preview).toBeEnabled());
  fireEvent.click(preview);
  fireEvent.click(await screen.findByRole('button', { name: 'Reset DEPO to vanilla state' }));
  const confirm = screen.getByRole('button', { name: 'Delete application data' });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Confirmation phrase'), { target: { value: 'RESET DEPO TO VANILLA' } });
  fireEvent.click(confirm);
  await screen.findByText(/Vanilla reset completed. Receipt: vanilla-test/);
  expect(API_METHODS.admin.resetVanilla).toHaveBeenCalledWith('preview-identity');
  expect(API_METHODS.admin.resetVanilla).toHaveBeenCalledTimes(1);
  expect(sessionStorage.getItem('bridge-workflow:old')).toBeNull();
  expect(sessionStorage.getItem('depo.browserSession.v1')).toBe('existing-delegated-access');
});

test('failed import cleanup retains browser history and displays the error', async () => {
  API_METHODS.admin.clearImportWorkflows.mockRejectedValue({ response: { data: { detail: 'Import tasks are active' } } });
  window.localStorage.setItem('depo.import.jobs.v2', 'retained');
  render(<AdminPanel />);
  const button = screen.getByRole('button', { name: 'Clear Import Workflows' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  fireEvent.change(screen.getByLabelText('Confirmation phrase'), { target: { value: 'CLEAR IMPORT WORKFLOWS' } });
  fireEvent.click(screen.getByRole('button', { name: 'Clear workflows' }));
  await screen.findByText('Import tasks are active');
  expect(window.localStorage.getItem('depo.import.jobs.v2')).toBe('retained');
});

test('partial cache failure remains visible after operational refresh', async () => {
  API_METHODS.admin.clearCache.mockResolvedValue({ data: { status: 'partial', message: 'Some caches could not be cleared.', cleared: { graph_cache: true, ontology_list_cache: false, config_cache: true } } });
  render(<AdminPanel />);
  const button = screen.getByRole('button', { name: /Clear.*cache/i });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  await screen.findByText('Some caches could not be cleared.');
  expect(API_METHODS.admin.clearCache).toHaveBeenCalledTimes(1);
});

test('destructive confirmation remains disabled until the exact phrase is entered', () => {
  const resolve = vi.fn();
  render(<ConfirmationDialog confirmation={{ title: 'Reset graph?', description: 'Deletes graph data.', phrase: 'RESET GRAPH', confirmLabel: 'Reset graph' }} onResolve={resolve} />);

  const confirm = screen.getByRole('button', { name: 'Reset graph' });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Confirmation phrase'), { target: { value: 'RESET GRAPH' } });
  expect(confirm).toBeEnabled();
  fireEvent.click(confirm);
  expect(resolve).toHaveBeenCalledWith(true);
});

test('destructive confirmation supports keyboard cancellation', () => {
  const resolve = vi.fn();
  render(<ConfirmationDialog confirmation={{ title: 'Delete schemas?', description: 'Deletes retained schemas.' }} onResolve={resolve} />);
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(resolve).toHaveBeenCalledWith(false);
});

test('a failed graph reset payload is shown as an error, not completion', async () => {
  API_METHODS.admin.resetDatabase.mockResolvedValue({ data: { status: 'FAIL', message: 'Index recreation failed after deletion.' } });
  render(<AdminPanel />);
  const button = screen.getByRole('button', { name: 'Reset Graph Only' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  fireEvent.change(await screen.findByLabelText('Confirmation phrase'), { target: { value: 'RESET GRAPH' } });
  fireEvent.click(screen.getByRole('button', { name: 'Reset graph' }));
  await screen.findByText('Index recreation failed after deletion.');
  expect(screen.queryByText(/Graph reset completed\./)).toBeNull();
});

test('cleanup stays disabled when maintenance access is absent', async () => {
  getCredentialProfile.mockReturnValue('');
  render(<AdminPanel />);
  await waitFor(() => expect(screen.getByRole('button', { name: /Clear Cache/i })).toBeDisabled());
  expect(screen.getByRole('button', { name: 'Full Schema Cleanup' })).toBeDisabled();
  expect(screen.getByText(/Enable Admin maintenance checked/)).toBeVisible();
  getCredentialProfile.mockReturnValue('test-maintenance-key');
});

test('partial reset refreshes state and keeps reconciliation warning visible', async () => {
  API_METHODS.admin.resetDatabase.mockResolvedValue({ data: { status: 'partial', message: 'Registry reconciliation failed.' } });
  render(<AdminPanel />);
  const button = screen.getByRole('button', { name: 'Reset Graph Only' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  fireEvent.change(await screen.findByLabelText('Confirmation phrase'), { target: { value: 'RESET GRAPH' } });
  fireEvent.click(screen.getByRole('button', { name: 'Reset graph' }));
  await screen.findByText('Registry reconciliation failed.');
  expect(screen.getByText(/Graph reset completed\./)).toBeVisible();
});
