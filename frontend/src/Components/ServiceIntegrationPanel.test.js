import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import ServiceIntegrationPanel from './ServiceIntegrationPanel';
import { apiClient } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('../config', () => ({ buildSemanticServiceUrl: (service, path) => `http://${service}${path}` }));
vi.mock('@siemens/ix-react', () => ({ IxButton: ({ children, ...props }) => <button {...props}>{children}</button> }));

test('integration cards display collection totals and all controls in content-driven articles', async () => {
  apiClient.get.mockImplementation(async url => ({ data: url.includes('oslc') ? { status: 'ok', server: 'enabled' } : { count: 100, total: 250, products: Array(100).fill({}) } }));
  render(<ServiceIntegrationPanel />);
  await waitFor(() => expect(screen.getAllByText('250')).toHaveLength(2));
  expect(screen.getByText('Not configured')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Refresh integrations' })).toBeEnabled();
  expect(screen.getByText('Data Catalog').closest('article')).toHaveClass('depo-service-card');
});

test('denied reads show service-specific errors without zero counts', async () => {
  apiClient.get.mockImplementation(async url => {
    if (url.includes('oslc')) return { data: { status: 'ok' } };
    throw { response: { status: 403 }, message: 'Forbidden' };
  });
  render(<ServiceIntegrationPanel />);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Data Catalog: access denied (403)'));
  expect(screen.getByRole('status')).toHaveTextContent('Data Products: access denied (403)');
  expect(screen.queryByText('0')).not.toBeInTheDocument();
});

test('empty registries explain why publication is needed', async () => {
  apiClient.get.mockImplementation(async url => ({ data: url.includes('oslc') ? { status: 'ok' } : { total: 0, products: [] } }));
  render(<ServiceIntegrationPanel />);
  await waitFor(() => expect(screen.getAllByText('0')).toHaveLength(2));
  expect(screen.getByText(/Publish an approved data-product draft/)).toBeVisible();
});

test('malformed responses cannot appear as zero', async () => {
  apiClient.get.mockImplementation(async url => ({ data: url.includes('oslc') ? { status: 'ok' } : { total: 0 } }));
  render(<ServiceIntegrationPanel />);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('invalid collection'));
  expect(screen.queryByText('0')).not.toBeInTheDocument();
});
