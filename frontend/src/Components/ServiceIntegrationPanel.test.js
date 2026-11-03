import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
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
  await waitFor(() => expect(screen.getByText(/Data Catalog: access denied/)).toHaveTextContent('(403)'));
  expect(screen.getByText(/Data Products: access denied/)).toHaveTextContent('(403)');
  expect(screen.queryByText('0')).not.toBeInTheDocument();
});

test('empty registries explain why publication is needed', async () => {
  apiClient.get.mockImplementation(async url => ({ data: url.includes('oslc') ? { status: 'ok' } : { total: 0, products: [] } }));
  render(<ServiceIntegrationPanel />);
  await waitFor(() => expect(screen.getAllByText('0')).toHaveLength(2));
  expect(screen.getByText(/No product packages are recorded/)).toBeVisible();
});

test('malformed responses cannot appear as zero', async () => {
  apiClient.get.mockImplementation(async url => ({ data: url.includes('oslc') ? { status: 'ok' } : { total: 0 } }));
  render(<ServiceIntegrationPanel />);
  await waitFor(() => expect(screen.getAllByRole('status')).toHaveLength(2));
  expect(screen.queryByText('0')).not.toBeInTheDocument();
});

test('unavailable OSLC does not imply an unconfigured provider or hide healthy products', async () => {
  apiClient.get.mockImplementation(async (url, options) => {
    expect(options.timeout).toBe(15000);
    if (url.includes('oslc')) throw new Error('OSLC unavailable');
    return {data:{total:2,products:[{},{}]}};
  });
  render(<ServiceIntegrationPanel />);
  await waitFor(() => expect(screen.getAllByText('2')).toHaveLength(2));
  expect(screen.queryByText('Not configured')).toBeNull();
  expect(screen.getByRole('link', {name:'Open Data Catalog'})).toHaveAttribute('href', '#/catalog');
  expect(screen.getByRole('link', {name:'Open Data Products'})).toHaveAttribute('href', '#/data-products');
  expect(screen.getByRole('button', {name:'Refresh integrations'})).toBeEnabled();
});

const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; };

test('catalog renders before slow OSLC and explains the count scope', async () => {
  const slow = deferred();
  apiClient.get.mockImplementation(url => url.includes('oslc') ? slow.promise : Promise.resolve({data:{total:0,products:[]}}));
  render(<ServiceIntegrationPanel />);
  await waitFor(() => expect(screen.getAllByText('0')).toHaveLength(2));
  expect(screen.getByText('Checking')).toBeVisible();
  expect(screen.getByText(/not imported sources or available analytics/)).toBeVisible();
  expect(screen.getByText(/not datasets or analytics tables/)).toBeVisible();
  await act(async () => slow.resolve({data:{status:'ok',remote_configured:true}}));
  expect(await screen.findByText('Address saved')).toBeVisible();
  expect(screen.getByText(/Connection and access have not been verified/)).toBeVisible();
});

test('reconnect ignores previous generation late responses', async () => {
  const old = deferred(); let generation = 0;
  apiClient.get.mockImplementation(url => url.includes('oslc') ? Promise.resolve({data:{status:'ok'}}) : generation === 0 ? old.promise : Promise.resolve({data:{total:0,products:[]}}));
  render(<ServiceIntegrationPanel />);
  await screen.findByText('ok');
  generation = 1;
  act(() => window.dispatchEvent(new Event('depo:credentials-changed')));
  await waitFor(() => expect(screen.getAllByText('0')).toHaveLength(2));
  await act(async () => old.resolve({data:{total:99,products:[{}]}}));
  expect(screen.queryByText('99')).not.toBeInTheDocument();
  expect(screen.getAllByText('0')).toHaveLength(2);
});
