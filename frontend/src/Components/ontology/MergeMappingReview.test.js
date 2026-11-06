import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import MergeMappingReview, { dictionaryTerms } from './MergeMappingReview';
import { API_METHODS } from '../../services/apiClient';

vi.mock('../../services/apiClient', () => ({ API_METHODS: { ontology: { getDataDictionary: vi.fn() } } }));
const candidate = { source_label: 'Diameter', source_iri: 'https://source/Diameter', target_label: 'DiameterType', target_iri: 'https://target/DiameterType', kind: 'class', reason: 'Same normalized label; requires review.' };
const defaults = { sourceId: 'ap242', targetId: 'qif', sourceLabel: 'AP242', targetLabel: 'QIF', onSelect: vi.fn() };

test('keeps duplicate human labels with their separate property identities', () => {
  const rows = dictionaryTerms({ properties: {
    status: { label: 'status', iri: 'urn:A:status' },
    'status [urn:B:status]': { label: 'status', iri: 'urn:B:status' },
  } });
  expect(rows.map(row => row.label)).toEqual(['status', 'status']);
  expect(rows.map(row => row.iri)).toEqual(['urn:A:status', 'urn:B:status']);
});

test('retains multiple reviewed pairs and removes one without clearing the other', () => {
  const second = {...candidate, source_iri:'https://source/Length', target_iri:'https://target/Length'};
  const onSelect = vi.fn();
  render(<MergeMappingReview {...defaults} suggestions={[candidate, second]}
    selectedMappings={[candidate, second]} onSelect={onSelect} />);
  expect(screen.getByText('2 pairs')).toBeVisible();
  expect(screen.getAllByRole('button', {name:'Selected — remove'})).toHaveLength(2);
  fireEvent.click(screen.getAllByRole('button', {name:'Selected — remove'})[0]);
  expect(onSelect).toHaveBeenCalledWith(candidate);
  expect(screen.getByText('Selected identity changes (2/200)')).toBeVisible();
});
beforeEach(() => { vi.clearAllMocks(); API_METHODS.ontology.getDataDictionary.mockResolvedValue({ data: { entities: { Diameter: { iri: 'https://terms/Diameter' } }, properties: {}, relationships: {} } }); });

test('browses both real vocabularies before agent suggestions exist', async () => {
  render(<MergeMappingReview {...defaults} />);
  fireEvent.click(screen.getByText('Browse source and target vocabularies'));
  await waitFor(() => expect(screen.getAllByText('Diameter')).toHaveLength(2));
  expect(API_METHODS.ontology.getDataDictionary.mock.calls.map(call => call[0])).toEqual(['ap242', 'qif']);
  expect(screen.getByText('Generate an agent preview to see proposed mappings')).toBeInTheDocument();
  expect(screen.getByText('Awaiting agent preview')).toBeInTheDocument();
  expect(API_METHODS.ontology.getDataDictionary.mock.calls.every(call => call[1].timeout === 90000 && call[1].signal)).toBe(true);
});

test('a slow vocabulary read keeps the saved proposals and offers a read-only retry', async () => {
  API_METHODS.ontology.getDataDictionary.mockRejectedValueOnce(new Error('The request timed out. Refresh operation status before retrying a write.'));
  render(<MergeMappingReview {...defaults} suggestions={[candidate]} />);
  fireEvent.click(screen.getByText('Browse source and target vocabularies'));
  await screen.findByText('Ontology term loading timed out. Retry term loading; saved merge proposals are retained.');
  expect(screen.getByText(candidate.source_iri)).toBeVisible();
  expect(screen.queryByText(/retrying a write/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'Retry term loading'}));
  await waitFor(() => expect(screen.queryByRole('button', {name:'Retry term loading'})).not.toBeInTheDocument());
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
  fireEvent.click(screen.getByText('Browse source and target vocabularies'));
  await waitFor(() => expect(screen.getAllByText('Diameter')).toHaveLength(2));
});
test('clearing selection removes consolidation, and conflicts remain visible', () => {
  render(<MergeMappingReview {...defaults} suggestions={[candidate]} sourceIri={candidate.source_iri} targetIri={candidate.target_iri} preview={{ conflicts: [{ reason: 'Incompatible definitions' }] }} />);
  expect(screen.getByText('1 conflicts block approval')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }));
  expect(defaults.onSelect).toHaveBeenCalledWith(null);
});

test('shows scored evidence, ambiguous alternatives and incomplete search without approving them', () => {
  const onSelect = vi.fn();
  render(<MergeMappingReview {...defaults} onSelect={onSelect} suggestions={[{...candidate,confidence_score:.72,ambiguous:true,score_components:{label_tokens:.8,character_trigrams:.6}}]} preview={{conflicts:[], matching_report:{policy:'lexical-context-v1',minimum_score:.55,comparisons:200,truncated:true}}} />);
  expect(screen.getByText('72% similarity')).toBeVisible();
  expect(screen.getByText('Ambiguous alternative')).toBeVisible();
  expect(screen.getByText(/these proposals are incomplete/)).toBeVisible();
  expect(onSelect).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Minimum mapping similarity'),{target:{value:'80'}});
  expect(screen.queryByRole('button',{name:'Select for consolidation'})).toBeNull();
});
