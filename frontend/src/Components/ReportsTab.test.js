import React from 'react';
import { vi } from 'vitest';
import { graphApi } from '../services/graphApi';
import { render, screen, waitFor } from '@testing-library/react';
import ReportsTab, { escapeCsv } from './ReportsTab';

vi.mock('../contexts/OntologyContext', () => ({
  OntologyProvider: ({ children }) => children,
  useOntologies: () => ({
    ontologies: [],
    loading: false,
    error: null,
    lastUpdated: null,
    fetchOntologies: vi.fn(),
    getOntologyByPrefix: vi.fn(),
    getOntologyById: vi.fn(),
  }),
}));

import { OntologyProvider } from '../contexts/OntologyContext';

test('CSV quotes fields using doubled quotes and preserves real newlines', () => {
  expect(escapeCsv('Part "A", revision\n2')).toBe('"Part ""A"", revision\n2"');
  expect(escapeCsv(null)).toBe('""');
});

vi.mock('../services/graphApi', () => ({ graphApi: { getOverview: vi.fn(async () => ({ data: { nodes: [], links: [] } })) } }));

vi.mock('../services/apiClient', () => ({
  apiClient: { get: vi.fn(async () => ({ data: {} })) },
  dataPipelineAPI: { telemetry: vi.fn(async () => ({ data: {} })) },
}));

test('ReportsTab does not substitute canvas data for an empty report projection', async () => {
  render(
    <OntologyProvider>
      <ReportsTab
        searchResults={[]}
        graphData={{
          nodes: [
            {
              elementId: 'n1',
              labels: ['Part'],
              label: 'Part',
              properties: { name: 'Rotor', part_number: 'P-100' },
            },
          ],
          links: [],
        }}
      />
    </OntologyProvider>
  );

  await waitFor(() => expect(graphApi.getOverview).toHaveBeenCalled());
  expect(screen.queryByText('Rotor')).toBeNull();
  expect(screen.getByText('Analytics overview')).toBeInTheDocument();
  expect(screen.getByText('Entity distribution')).toBeInTheDocument();
  expect(screen.getByText('Relationship distribution')).toBeInTheDocument();
  expect(screen.getByText('Ontology coverage')).toBeInTheDocument();
  expect(screen.getByText('Data-job status')).toBeInTheDocument();
  expect(screen.getByText('Data-quality outcome')).toBeInTheDocument();
});
