import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import ReportsTab, { escapeCsv } from './ReportsTab';

jest.mock('../contexts/OntologyContext', () => ({
  OntologyProvider: ({ children }) => children,
  useOntologies: () => ({
    ontologies: [],
    loading: false,
    error: null,
    lastUpdated: null,
    fetchOntologies: jest.fn(),
    getOntologyByPrefix: jest.fn(),
    getOntologyById: jest.fn(),
  }),
}));

import { OntologyProvider } from '../contexts/OntologyContext';

test('CSV quotes fields using doubled quotes and preserves real newlines', () => {
  expect(escapeCsv('Part "A", revision\n2')).toBe('"Part ""A"", revision\n2"');
  expect(escapeCsv(null)).toBe('""');
});

jest.mock('../services/graphApi', () => ({ graphApi: { getOverview: jest.fn(async () => ({ data: { nodes: [], links: [] } })) } }));

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

  await waitFor(() => expect(screen.queryByText('Rotor')).toBeNull());
  expect(screen.getByText('Analytics overview')).toBeInTheDocument();
  expect(screen.getByText('Entity distribution')).toBeInTheDocument();
  expect(screen.getByText('Relationship distribution')).toBeInTheDocument();
  expect(screen.getByText('Ontology coverage')).toBeInTheDocument();
  expect(screen.getByText('Data-job status')).toBeInTheDocument();
  expect(screen.getByText('Data-quality outcome')).toBeInTheDocument();
});
