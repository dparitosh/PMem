import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { vi } from 'vitest';
import CredentialSettings from './CredentialSettings';
import { clearServiceAuthToken, getCredentialProfile, setCredentialProfile, setBrowserSessionExpiry } from '../services/serviceAuth';

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
  return within(input.closest('tr'));
};
const response = (status, body) => ({ ok: status === 200, status, json: async () => body });

test('restored central session is checked without displaying individual keys', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_restored');
  setBrowserSessionExpiry('depo_session_restored', new Date(Date.now() + 600000).toISOString());
  fetch.mockResolvedValue(response(200, { status: 'authorized' }));
  render(<CredentialSettings />);
  await waitFor(() => expect(screen.getAllByText(/Read session verified: graph, agentic/).length).toBeGreaterThan(0));
  expect(screen.getByLabelText('GRAPH_READ_TOKEN')).toHaveValue('');
  expect(screen.getByLabelText('GRAPH_READ_TOKEN')).toHaveAttribute('placeholder', 'Using central session — key not displayed');
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer depo_session_restored');
  expect(screen.getByLabelText(/Enable Admin maintenance/)).not.toBeChecked();
});

test('restored session rejection reports the actual service detail and clears invalid access', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_restored');
  setBrowserSessionExpiry('depo_session_restored', new Date(Date.now() + 600000).toISOString());
  fetch.mockResolvedValue(response(403, { detail: 'Browser session scope is unavailable or credentials changed; reconnect in Admin' }));
  render(<CredentialSettings />);
  await waitFor(() => expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe(''));
  await waitFor(() => expect(screen.getAllByText(/graph: HTTP 403; Browser session scope/).length).toBeGreaterThan(0));
});

test('one admin connection applies registered scopes without exposing their keys', async () => {
  fetch.mockResolvedValueOnce(response(200, { token: 'depo_session_opaque', expires_at: new Date(Date.now() + 600000).toISOString(), profiles: ['GRAPH_READ_TOKEN', 'INGESTION_WRITE_TOKEN', 'ADMIN_API_KEY'] }))
    .mockResolvedValue(response(200, { status: 'authorized' }));
  render(<CredentialSettings />);
  fireEvent.change(screen.getByLabelText('Administrator key for connection'), { target: { value: 'admin-fixture' } });
  fireEvent.click(screen.getByLabelText('Enable registered upload, execution and approval scopes for this session'));
  fireEvent.click(screen.getByRole('button', { name: 'Connect registered services' }));
  await waitFor(() => expect(getCredentialProfile('INGESTION_WRITE_TOKEN')).toBe('depo_session_opaque'));
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('depo_session_opaque');
  expect(getCredentialProfile('ADMIN_API_KEY')).toBe('depo_session_opaque');
  expect(screen.getByLabelText(/Enable Admin maintenance/)).toBeChecked();
  expect(screen.getByLabelText('Administrator key for connection')).toHaveValue('');
  expect(screen.getByLabelText('GRAPH_READ_TOKEN')).toHaveValue('');
  const [url, options] = fetch.mock.calls[0];
  expect(url).toBe('http://ontology/auth/browser-session');
  expect(options.headers['X-API-Key']).toBe('admin-fixture');
  expect(JSON.parse(options.body)).toEqual({ include_writes: true, include_maintenance: true });
  const saved = sessionStorage.getItem('depo.browserSession.v1');
  expect(JSON.parse(saved).profiles).toContain('ADMIN_API_KEY');
  expect(saved).not.toContain('admin-fixture');
  expect(screen.getAllByRole('button', {name:'Register / rotate in database'}).every(button => button.disabled)).toBe(true);
});

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
