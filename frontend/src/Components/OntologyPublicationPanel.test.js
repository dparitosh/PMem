import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { apiClient } from '../services/apiClient';
import OntologyPublicationPanel from './OntologyPublicationPanel';
afterEach(() => vi.restoreAllMocks());
test('registration stays separate from publication and approval is required', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({ data: url.endsWith('/publication') ? { status: 'not_published' } : { lifecycle_status: 'draft' } }));
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });
  render(<OntologyPublicationPanel ontologyId="demo" />);
  await screen.findByText('Submit for review');
  expect(screen.queryByText('Publish to Neo4j')).toBeNull();
  expect(post).not.toHaveBeenCalled();
});
test('an approved ontology publishes only on an explicit user action', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({ data: url.endsWith('/publication') ? { status: 'not_published' } : { lifecycle_status: 'approved' } }));
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });
  render(<OntologyPublicationPanel ontologyId="demo" />);
  const button = await screen.findByText('Publish to Neo4j');
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByPlaceholderText('Your approval identity'), { target: { value: 'reviewer' } });
  fireEvent.click(button);
  expect(post).toHaveBeenCalledWith(expect.stringContaining('/demo/publish'), expect.objectContaining({ approved_by: 'reviewer' }), expect.objectContaining({ signal: expect.any(AbortSignal) }));
  await waitFor(() => expect(screen.getByText('Publish to Neo4j')).toBeEnabled());
});

test('malformed lifecycle data cannot render approval controls', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({data:url.endsWith('/publication') ? {status:'not_published'} : {lifecycle_status:{approved:true}}}));
  render(<OntologyPublicationPanel ontologyId="bad" />);
  await screen.findByRole('alert');
  expect(screen.queryByText('Publish to Neo4j')).toBeNull();
});

test('changing credentials clears the pending approver identity', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({data:url.endsWith('/publication') ? {status:'not_published'} : {lifecycle_status:'approved'}}));
  render(<OntologyPublicationPanel ontologyId="demo" />);
  await screen.findByText('Publish to Neo4j');
  fireEvent.change(screen.getByPlaceholderText('Your approval identity'), {target:{value:'previous-user'}});
  fireEvent(window, new Event('depo:credentials-changed'));
  expect(screen.getByPlaceholderText('Your approval identity')).toHaveValue('');
});
