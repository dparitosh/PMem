import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { VocabularyTable } from './OntologyMapper';

const edges = Array.from({length: 60}, (_, i) => ({
  source_term: `source:Term${i + 1}`, target_term: `target:Term${i + 1}`,
  source_label: `Source ${i + 1}`, target_label: `Target ${i + 1}`, mapping_type: 'mapsTo',
}));

test('mapping pages preserve row numbers and reset after filtering or replacement', () => {
  const {rerender} = render(<VocabularyTable edges={edges} filter="" />);
  expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
  expect(screen.getByText('1–25 of 60 mappings')).toBeInTheDocument();
  expect(screen.getByRole('button', {name:'Previous'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button', {name:'Next'}));
  expect(screen.getByText('26–50 of 60 mappings')).toBeInTheDocument();
  expect(within(screen.getByRole('table')).getByText('26')).toBeInTheDocument();
  expect(screen.queryByText('Source 1')).toBeNull();
  fireEvent.click(screen.getByRole('button', {name:'Next'}));
  expect(screen.getByText('51–60 of 60 mappings')).toBeInTheDocument();
  expect(screen.getByRole('button', {name:'Next'})).toBeDisabled();
  rerender(<VocabularyTable edges={edges} filter="Source 1" />);
  expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
  expect(screen.getByText('Source 1')).toBeInTheDocument();
  rerender(<VocabularyTable edges={edges.slice(0, 1)} filter="" />);
  expect(screen.getByText('1–1 of 1 mappings')).toBeInTheDocument();
});

test('page size resets selection and empty filters disable navigation', () => {
  const {rerender} = render(<VocabularyTable edges={edges} filter="" />);
  fireEvent.click(screen.getByRole('button', {name:'Next'}));
  fireEvent.change(screen.getByLabelText('Mappings per page'), {target:{value:'50'}});
  expect(screen.getByText('1–50 of 60 mappings')).toBeInTheDocument();
  expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
  rerender(<VocabularyTable edges={edges} filter="no matching term" />);
  expect(screen.getByText('0 mappings')).toBeInTheDocument();
  expect(screen.getByRole('button', {name:'Previous'})).toBeDisabled();
  expect(screen.getByRole('button', {name:'Next'})).toBeDisabled();
});
