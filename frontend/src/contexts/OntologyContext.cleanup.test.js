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

test('native catalog follows bounded pages and merges all ontology identities', async () => {
  mocks.get.mockImplementation(path => Promise.resolve({ data: path.includes('offset=200')
    ? { ontologies: [{ ontology_id: 'target', name: 'Target' }], next_offset: null }
    : path.includes('/ontologies?')
      ? { ontologies: [{ ontology_id: 'source', name: 'Source' }], next_offset: 200 }
      : { ontologies: [] } }));
  render(<OntologyProvider><Registry /></OntologyProvider>);
  await screen.findByText('Source,Target');
  expect(mocks.get).toHaveBeenCalledWith('/api/v1/ontologies?limit=200&offset=200', expect.any(Object));
});

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

test('catalog authorization failure remains visible alongside a registry timeout', async () => {
  mocks.get.mockImplementation(path => Promise.reject(path.startsWith('/api/v1/ontologies')
    ? {response:{status:403,data:{detail:'Required API key is missing or invalid'}}}
    : {code:'ECONNABORTED'}));
  render(<OntologyProvider><Registry /></OntologyProvider>);
  const alert=await screen.findByRole('alert');
  expect(alert).toHaveTextContent('Ontology catalog (Required API key is missing or invalid)');
  expect(alert).toHaveTextContent('Ingestion registry (The request timed out.');
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

test('session expiry removes previously visible ontology registrations', async () => {
  mocks.get.mockResolvedValue({data:{ontologies:[{ontology_id:'private',name:'Previous session ontology'}]}});
  render(<OntologyProvider><Registry /></OntologyProvider>);
  await screen.findByText('Previous session ontology');
  mocks.get.mockRejectedValue(new Error('Access expired'));
  act(() => window.dispatchEvent(new Event('depo:session-expired')));
  await screen.findByText('Empty registry');
  expect(screen.queryByText('Previous session ontology')).not.toBeInTheDocument();
});

test('session replacement discards the previous registry and cancels its pending refresh',async()=>{
 mocks.get.mockResolvedValue({data:{ontologies:[{ontology_id:'old',name:'Previous identity ontology'}]}});
 render(<OntologyProvider><Registry/></OntologyProvider>);
 await screen.findByText('Previous identity ontology');
 mocks.get.mockImplementation(()=>new Promise(()=>{}));
 act(()=>window.dispatchEvent(new Event('depo:session-replaced')));
 expect(screen.queryByText('Previous identity ontology')).toBeNull();
 expect(screen.getByText('Empty registry')).toBeVisible();
});

test('access revalidation retains the current registry while its read is pending or fails', async () => {
  mocks.get.mockResolvedValue({data:{ontologies:[{ontology_id:'part',name:'Retained product ontology'}]}});
  render(<OntologyProvider><Registry /></OntologyProvider>);
  await screen.findByText('Retained product ontology');
  const rejects = [];
  mocks.get.mockImplementation(() => new Promise((_resolve, reject) => rejects.push(reject)));
  act(() => window.dispatchEvent(new Event('depo:access-verified')));
  expect(screen.getByText('Retained product ontology')).toBeVisible();
  await act(async () => rejects.forEach(reject => reject({code:'ERR_NETWORK'})));
  await screen.findByRole('alert');
  expect(screen.getByText('Retained product ontology')).toBeVisible();
});
