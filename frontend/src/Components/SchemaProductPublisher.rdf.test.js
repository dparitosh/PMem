import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, test, expect } from 'vitest';
import SchemaProductPublisher from './SchemaProductPublisher';
import { productDraftFromOntology } from '../services/analyticsProductDraft';
import { apiClient } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { post: vi.fn() } }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: () => 'fixture-token', publicationRecoveryScope: () => 'rdf-test' }));
vi.mock('../config', () => ({ buildSemanticServiceUrl: (_service, path) => path }));
vi.mock('@siemens/ix-react', () => ({ IxButton: ({ children, ...props }) => <button {...props}>{children}</button> }));

test('real RDF builder validates and publishes with selected ontology lineage', async () => {
  sessionStorage.clear();
  apiClient.post.mockImplementation(async url => ({ data: url.endsWith('/preview') ? { valid: true } : { product_id: 'rdf_product', version: '1.0.0', status: 'published' } }));
  const draft = productDraftFromOntology({ ontology_id: 'registered-ontology', prefix: 'spqm', artifact_id: 'rdf-artifact',
    data_product_draft: { contract: 'ontology-evidence-data-product-v1', product_kind: 'ontology-evidence', name: 'Ontology evidence', quality_status: 'requires_review', artifacts: [{ artifact_id: 'rdf-artifact' }] } });
  render(<SchemaProductPublisher draft={draft} />);
  expect(screen.queryByText('Inspect an XSD with dependency files')).toBeNull();
  expect(screen.getByRole('button', { name: 'Approve and publish evidence' })).toBeDisabled();
  for (const [label, value] of Object.entries({ 'Product ID': 'rdf_product', Owner: 'owner', Steward: 'steward', Approver: 'approver', 'Approved semantic asset ID': 'approved-release', 'Approved semantic release version': '1.0.0' })) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.click(screen.getByRole('button', { name: 'Validate publication contract' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve and publish evidence' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Approve and publish evidence' }));
  await screen.findByText(/rdf_product@1.0.0: published/);
  const payload = apiClient.post.mock.calls.find(([url]) => url.endsWith('/publish'))[1];
  expect(payload.product_kind).toBe('ontology-evidence');
  expect(payload.ontologies[0].ontology_id).toBe('registered-ontology');
  expect(payload.sources[0].ontology_id).toBe('registered-ontology');
  expect(payload.semantic_releases[0].asset_id).toBe('approved-release');
  expect(payload.quality_status).toBe('requires_review');
});
