import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import AdminPanel, { ConfirmationDialog } from './AdminPanel';
import { API_METHODS } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ API_METHODS: { admin: {
  health: vi.fn(async () => ({ data: { status: 'ok' } })),
  schemaStats: vi.fn(async () => ({ data: { stats: {} } })),
  clearCache: vi.fn(),
  resetDatabase: vi.fn(),
}, agentic: { isConfigured: () => false } } }));
vi.mock('../contexts/OntologyContext', () => ({ useOntologies: () => ({ fetchOntologies: async () => {} }) }));

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
