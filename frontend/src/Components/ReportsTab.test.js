import React from 'react';
import { render, screen } from '@testing-library/react';
import ReportsTab from './ReportsTab';

test('ReportsTab falls back to graph nodes when search results are empty', () => {
  render(
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
  );

  expect(screen.getByText('Rotor')).toBeInTheDocument();
  expect(screen.getAllByText('Part').length).toBeGreaterThan(0);
});
