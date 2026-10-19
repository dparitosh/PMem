import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import MergeMappingReview from './MergeMappingReview';
import { API_METHODS } from '../../services/apiClient';

vi.mock('../../services/apiClient', () => ({ API_METHODS: { ontology: { getDataDictionary: vi.fn() } } }));
const candidate = { source_label: 'Diameter', source_iri: 'https://source/Diameter', target_label: 'DiameterType', target_iri: 'https://target/DiameterType', kind: 'class', reason: 'Same normalized label; requires review.' };
const defaults = { sourceId: 'ap242', targetId: 'qif', sourceLabel: 'AP242', targetLabel: 'QIF', onSelect: vi.fn() };
beforeEach(() => { vi.clearAllMocks(); API_METHODS.ontology.getDataDictionary.mockResolvedValue({ data: { entities: { Diameter: { iri: 'https://terms/Diameter' } }, properties: {}, relationships: {} } }); });

test('browses both real vocabularies before agent suggestions exist', async () => {
  render(<MergeMappingReview {...defaults} />);
  await waitFor(() => expect(screen.getAllByText('Diameter')).toHaveLength(2));
  expect(API_METHODS.ontology.getDataDictionary.mock.calls.map(call => call[0])).toEqual(['ap242', 'qif']);
  expect(screen.getByText('Generate an agent preview to see proposed mappings')).toBeInTheDocument();
  expect(screen.getByText('Awaiting agent preview')).toBeInTheDocument();
});
test('shows exact source and target identifiers and passes the reviewed pair without approving it', async () => {
  render(<MergeMappingReview {...defaults} suggestions={[candidate]} preview={{ triple_count: 42, conflicts: [] }} />);
  expect(screen.getByText(candidate.source_iri)).toBeInTheDocument();
  expect(screen.getByText(candidate.target_iri)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Select for consolidation' }));
  expect(defaults.onSelect).toHaveBeenCalledWith(candidate);
  fireEvent.change(screen.getByRole('textbox', { name: 'Search proposed mappings' }), { target: { value: 'unmatched' } });
  expect(screen.queryByRole('button', { name: 'Select for consolidation' })).not.toBeInTheDocument();
});
test('distinguishes preview failure from zero conflicts and permits independent dictionary inspection', async () => {
  render(<MergeMappingReview {...defaults} error="Preview rejected (422)" />);
  expect(screen.getByText('Agent preview did not complete')).toBeInTheDocument();
  expect(screen.getByText('No mapping approval is available. Term browsing remains available below.')).toBeInTheDocument();
  await waitFor(() => expect(screen.getAllByText('Diameter')).toHaveLength(2));
});
test('clearing selection removes consolidation, and conflicts remain visible', () => {
  render(<MergeMappingReview {...defaults} suggestions={[candidate]} sourceIri={candidate.source_iri} targetIri={candidate.target_iri} preview={{ conflicts: [{ reason: 'Incompatible definitions' }] }} />);
  expect(screen.getByText('1 conflicts block approval')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }));
  expect(defaults.onSelect).toHaveBeenCalledWith(null);
});
