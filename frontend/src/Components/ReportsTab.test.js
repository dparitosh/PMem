import React from 'react';
import { render, screen } from '@testing-library/react';
import ReportsTab from './ReportsTab';
import { OntologyProvider } from '../contexts/OntologyContext';

test('ReportsTab falls back to graph nodes when search results are empty', () => {
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

  expect(screen.getByText('Rotor')).toBeInTheDocument();
  expect(screen.getAllByText('Part').length).toBeGreaterThan(0);
});
