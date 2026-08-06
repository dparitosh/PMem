import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import GraphExplorerToolbar from './GraphExplorerToolbar';

const theme = {
  surface: '#fff',
  surfaceMuted: '#f5f5f5',
  surfaceAccent: '#eef4fa',
  border: '#ddd',
  borderStrong: '#bbb',
  primary: '#005a9c',
  ink: '#111',
  inkSoft: '#555',
};

const renderToolbar = (overrides = {}) => render(
  <GraphExplorerToolbar
    theme={theme}
    graphViewMode="ontology"
    selectedOntology="ALL"
    searchInput=""
    searchResultMode="best"
    selectedStepPart="ALL"
    getRelationshipVisual={() => ({ color: '#777', width: 1, dasharray: '' })}
    {...overrides}
  />
);

test('renders safely while ontology and STEP options are unavailable', () => {
  renderToolbar();

  expect(screen.getByRole('combobox', { name: /select an ontology/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
});

test('submits the controlled search value and clears active search', () => {
  const onSearchSubmit = jest.fn();
  const onSearchInputChange = jest.fn();
  renderToolbar({
    searchInput: 'bearing',
    graphSearchActive: true,
    onSearchSubmit,
    onSearchInputChange,
  });

  fireEvent.submit(screen.getByRole('button', { name: 'Search' }).closest('form'));
  expect(onSearchSubmit).toHaveBeenCalledWith('bearing');

  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  expect(onSearchInputChange).toHaveBeenCalledWith('');
  expect(onSearchSubmit).toHaveBeenCalledWith('');
});
