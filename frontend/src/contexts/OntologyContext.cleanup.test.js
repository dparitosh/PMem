import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { OntologyProvider, useOntologies } from './OntologyContext';
const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../services/apiClient', () => ({ apiClient: { get: mocks.get } }));
vi.mock('../config', () => ({ buildUrl: path => path }));
vi.mock('../utils/logger', () => ({ default: { error: vi.fn() } }));

function Registry() {
  const { ontologies, error } = useOntologies();
  return <><span>{ontologies.map(row => row.name).join(',') || 'Empty registry'}</span>{error && <span role="alert">{error}</span>}</>;
}

test('cleanup removes displayed registrations even when refresh fails', async () => {
  mocks.get.mockResolvedValue({ data: { ontologies: [{ ontology_id: 'qif', name: 'QIF' }] } });
  render(<OntologyProvider><Registry /></OntologyProvider>);
  await screen.findByText('QIF');
  mocks.get.mockRejectedValue(new Error('Service unavailable'));
  act(() => window.dispatchEvent(new Event('dt-schema-cleaned')));
  await screen.findByText('Empty registry');
  await screen.findByRole('alert');
  expect(screen.queryByText('QIF')).toBeNull();
});

test('cleanup aborts a registry request that started before deletion', async () => {
  const signals = [];
  mocks.get.mockImplementation((_path, options) => {
    signals.push(options.signal);
    return new Promise(() => {});
  });
  render(<OntologyProvider><Registry /></OntologyProvider>);
  await waitFor(() => expect(signals).toHaveLength(2));
  act(() => window.dispatchEvent(new Event('dt-schema-cleaned')));
  await waitFor(() => expect(signals).toHaveLength(4));
  expect(signals[0].aborted).toBe(true);
  expect(signals[1].aborted).toBe(true);
  expect(signals[2].aborted).toBe(false);
});
