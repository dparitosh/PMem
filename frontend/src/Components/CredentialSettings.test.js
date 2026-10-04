import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { vi } from 'vitest';
import CredentialSettings from './CredentialSettings';
import { clearServiceAuthToken, getCredentialProfile, setCredentialProfile } from '../services/serviceAuth';

vi.mock('../config', () => ({
  config: { gatewayUrl: '', semanticServiceUrls: { graph: 'http://graph', agentic: 'http://agentic' } },
  buildSemanticServiceUrl: (service, path) => `http://${service}${path}`,
}));
vi.mock('../app/ServiceAccessDiscovery', () => ({ default: () => <div>Contract discovery</div> }));

beforeEach(() => { clearServiceAuthToken(); vi.stubGlobal('fetch', vi.fn()); });
afterEach(() => { clearServiceAuthToken(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const enter = (profile, value) => {
  const input = screen.getByLabelText(profile);
  fireEvent.change(input, { target: { value } });
  return within(input.closest('div'));
};
const response = (status, body) => ({ ok: status === 200, status, json: async () => body });

test('read key is applied only after every configured service accepts it', async () => {
  fetch.mockResolvedValue(response(200, { status: 'authorized' }));
  render(<CredentialSettings />);
  fireEvent.click(enter('GRAPH_READ_TOKEN', 'read-fixture').getByRole('button', { name: 'Test and apply' }));
  await screen.findByText('Validated and applied: graph, agentic');
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('read-fixture');
  fireEvent.click(screen.getByRole('button', { name: 'Clear credentials' }));
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('');
  expect(screen.getByLabelText('GRAPH_READ_TOKEN')).toHaveValue('');
});

test('partial read rejection preserves the previously applied key', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'previous');
  fetch.mockResolvedValueOnce(response(200, { status: 'authorized' }))
    .mockResolvedValueOnce(response(403, { detail: 'key rejected' }));
  render(<CredentialSettings />);
  fireEvent.click(enter('GRAPH_READ_TOKEN', 'new-key').getByRole('button', { name: 'Test and apply' }));
  await screen.findByText('graph: authorized; agentic: key rejected');
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('previous');
});

test('administrator validation uses X-API-Key and does not rotate credentials', async () => {
  fetch.mockResolvedValue(response(200, { status: 'authorized' }));
  render(<CredentialSettings />);
  fireEvent.click(enter('ADMIN_API_KEY', 'admin-fixture').getByRole('button', { name: 'Test and apply' }));
  await waitFor(() => expect(getCredentialProfile('ADMIN_API_KEY')).toBe('admin-fixture'));
  const [url, options] = fetch.mock.calls[0];
  expect(url).toBe('http://ontology/auth/admin-access');
  expect(options.headers['X-API-Key']).toBe('admin-fixture');
  expect(options.headers.Authorization).toBeUndefined();
  expect(options.method).toBeUndefined();
});
