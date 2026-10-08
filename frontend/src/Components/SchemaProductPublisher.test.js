import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import SchemaProductPublisher from './SchemaProductPublisher';
import { apiClient } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { post: vi.fn() } }));
const recovery = vi.hoisted(() => ({ scope: 'deployment-a' }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: () => 'test-token', publicationRecoveryScope: () => recovery.scope }));
vi.mock('../config', () => ({ buildSemanticServiceUrl: (_service, path) => path }));
vi.mock('../services/analyticsProductDraft', () => ({ publicationFromDraft: () => ({ product_id: 'a' }), isDefinitivePublicationRejection: () => false }));
vi.mock('@siemens/ix-react', () => ({ IxButton: ({ children, ...props }) => <button {...props}>{children}</button> }));
beforeEach(() => { sessionStorage.clear(); recovery.scope = 'deployment-a'; });

test('uncertain publication survives unmount with the same payload', async () => {
  apiClient.post.mockReset();
  apiClient.post.mockImplementation(async url => {
    if (url.endsWith('/preview')) return { data: { valid: true } };
    throw new Error('Network interruption');
  });
  const draft = { name: 'Recoverable draft' };
  const view = render(<SchemaProductPublisher draft={draft} />);
  fireEvent.click(screen.getByRole('button', { name: 'Validate publication contract' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve and publish evidence' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Approve and publish evidence' }));
  await screen.findByText('Network interruption');
  const original = apiClient.post.mock.calls.find(([url]) => url.endsWith('/publish'))[1];
  view.unmount();
  render(<SchemaProductPublisher draft={draft} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Retry same publication' }));
  await waitFor(() => expect(apiClient.post.mock.calls.filter(([url]) => url.endsWith('/publish'))).toHaveLength(2));
  expect(apiClient.post.mock.calls.filter(([url]) => url.endsWith('/publish'))[1][1]).toEqual(original);
});

test('a different deployment cannot recover an old publication', () => {
  const draft = { name: 'Shared draft' };
  sessionStorage.setItem(`depo:pending-publication:${JSON.stringify(['deployment-a', draft])}`,
    JSON.stringify({ scope: 'deployment-a', payload: { product_id: 'a' }, draft, fields: { name: 'Old publication' } }));
  recovery.scope = 'deployment-b';
  render(<SchemaProductPublisher draft={draft} />);
  expect(screen.queryByRole('button', { name: 'Retry same publication' })).toBeNull();
  expect(screen.getByLabelText('Product name')).toHaveValue('Shared draft');
});

for (const change of ['root', 'dependencies', 'paths']) {
  test(`changing ${change} prevents publication of the previously inspected draft`, async () => {
    apiClient.post.mockImplementation(async url => ({ data: url.endsWith('/inspect') ? { data_product_draft: { name: 'A', analytics_readiness: 'review' } } : { valid: true } }));
    render(<SchemaProductPublisher draft={{ name: 'Existing' }} />);
    fireEvent.click(screen.getByText('Inspect an XSD with dependency files'));
    fireEvent.change(screen.getByLabelText('Root XSD'), { target: { files: [new File(['a'], 'a.xsd')] } });
    fireEvent.click(screen.getByRole('button', { name: 'Inspect schema set' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Validate publication contract' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Validate publication contract' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Approve and publish evidence' })).toBeEnabled());
    if (change === 'root') fireEvent.change(screen.getByLabelText('Root XSD'), { target: { files: [new File(['b'], 'b.xsd')] } });
    if (change === 'dependencies') fireEvent.change(screen.getByLabelText('Dependency XSD files'), { target: { files: [new File(['b'], 'b.xsd')] } });
    if (change === 'paths') fireEvent.change(screen.getByLabelText(/Relative paths/), { target: { value: 'types/b.xsd' } });
    expect(screen.queryByRole('button', { name: 'Approve and publish evidence' })).not.toBeInTheDocument();
    expect(screen.getByText(/Inspect the schema set again/)).toBeVisible();
  });
}

test('an uncertain publication retains its original payload across draft refreshes', async () => {
  apiClient.post.mockReset();
  apiClient.post.mockImplementation(async url => {
    if (url.endsWith('/preview')) return {data:{valid:true}};
    throw Object.assign(new Error('Network interruption'), {code:'ERR_NETWORK'});
  });
  const view = render(<SchemaProductPublisher draft={{name:'Original draft'}} />);
  fireEvent.click(screen.getByRole('button', {name:'Validate publication contract'}));
  await waitFor(() => expect(screen.getByRole('button', {name:'Approve and publish evidence'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button', {name:'Approve and publish evidence'}));
  await screen.findByText(/Publication outcome may be uncertain/);
  const original = apiClient.post.mock.calls.find(([url]) => url.endsWith('/publish'))[1];
  view.rerender(<SchemaProductPublisher draft={{name:'Refreshed draft'}} />);
  fireEvent.click(screen.getByRole('button', {name:'Retry same publication'}));
  await waitFor(() => expect(apiClient.post.mock.calls.filter(([url]) => url.endsWith('/publish'))).toHaveLength(2));
  const retry = apiClient.post.mock.calls.filter(([url]) => url.endsWith('/publish'))[1][1];
  expect(retry).toBe(original);
  expect(screen.getByLabelText('Product name')).toHaveValue('Original draft');
});
