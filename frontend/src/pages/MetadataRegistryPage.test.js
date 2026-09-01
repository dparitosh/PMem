import React from 'react';
import { vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import MetadataRegistryPage from './MetadataRegistryPage';
import { API_METHODS } from '../services/apiClient';

vi.mock('../contexts/OntologyContext', () => ({
  useOntologies: () => ({
    ontologies: [{ ontology_id: 'onto-1', label: 'Fallback Ontology', prefix: 'fallback', status: 'approved' }],
    loading: false,
    error: null,
    lastUpdated: null,
    fetchOntologies: vi.fn(),
  }),
}));

vi.mock('../services/apiClient', () => ({
  API_METHODS: {
    metadataRegistry: {
      list: vi.fn(),
      create: vi.fn(),
      transition: vi.fn(),
    },
    ontology: {
      getDataDictionary: vi.fn(),
    },
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
});

test('shows a successfully loaded empty governed registry instead of ontology fallback rows', async () => {
  API_METHODS.metadataRegistry.list.mockResolvedValue({ data: { assets: [] } });

  render(<MetadataRegistryPage />);

  expect(await screen.findByText('No governed metadata assets are registered yet.')).toBeInTheDocument();
  expect(screen.queryByText('Fallback Ontology')).not.toBeInTheDocument();
});

test('uses the valid draft to in-review lifecycle transition and prevents duplicate clicks', async () => {
  API_METHODS.metadataRegistry.list.mockResolvedValue({
    data: {
      assets: [{
        asset_id: 'asset-1',
        name: 'Part number',
        asset_type: 'DataElement',
        lifecycle_status: 'draft',
        version: '1.0.0',
      }],
    },
  });
  let resolveTransition;
  API_METHODS.metadataRegistry.transition.mockReturnValue(new Promise((resolve) => {
    resolveTransition = resolve;
  }));

  render(<MetadataRegistryPage />);
  const action = await screen.findByRole('button', { name: 'Submit for review' });
  expect(screen.getByText('Published / available').parentElement).toHaveTextContent('0');
  expect(screen.getByText('Review required').parentElement).toHaveTextContent('1');
  fireEvent.click(action);
  fireEvent.click(action);

  expect(API_METHODS.metadataRegistry.transition).toHaveBeenCalledTimes(1);
  expect(API_METHODS.metadataRegistry.transition).toHaveBeenCalledWith(
    'asset-1',
    expect.objectContaining({ status: 'in_review' }),
    expect.objectContaining({ signal: expect.any(AbortSignal) })
  );

  resolveTransition({ data: { asset_id: 'asset-1', name: 'Part number', lifecycle_status: 'in_review', version: '1.0.0' } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument());
});
