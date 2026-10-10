import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import AdminPage from './AdminPage';
import { API_METHODS } from '../services/apiClient';

vi.mock('../Components/CredentialSettings', () => ({ default: () => <label>Administrator key<input aria-label="Administrator key" /></label> }));
vi.mock('../Components/AdminPanel', () => ({ default: () => <div>Cleanup controls</div> }));
vi.mock('../Components/AgentControlPanel', () => ({ default: () => <div>Workflow controls</div> }));
vi.mock('../Components/AgentProposalPanel', () => ({ default: () => <div>Agent recommendations</div> }));
vi.mock('../Components/ServiceIntegrationPanel', () => ({ default: () => <div>Integration health</div> }));
vi.mock('../widgets/RegistryWidget', () => ({ default: ({ title }) => <div>{title}</div> }));
vi.mock('../widgets/KpiStrip', () => ({ default: ({ items }) => <div>{items.map(item => <span key={item.label} data-testid={`count-${item.label}`}>{item.value ?? '—'}</span>)}</div> }));
vi.mock('../services/apiClient', () => ({ API_METHODS: {admin:{registry:vi.fn(async () => ({data:{}}))}} }));
vi.mock('../services/agenticApi', () => ({default:{isEnabled:()=>true,isConfigured:()=>true,listAgents:async()=>({data:{agents:[]}}),listTools:async()=>({data:{tools:[]}})}}));
beforeEach(() => sessionStorage.clear());

test('Admin groups sections and preserves credential input when switching tabs', async () => {
  render(<AdminPage />);
  expect(screen.getByRole('tabpanel', {name:'Overview'})).toBeVisible();
  fireEvent.click(screen.getByRole('tab', {name:'API access'}));
  fireEvent.change(screen.getByLabelText('Administrator key'), {target:{value:'draft-key'}});
  fireEvent.click(screen.getByRole('tab', {name:'Agents & workflows'}));
  expect(screen.getByText('Workflow controls')).toBeVisible();
  expect(screen.queryByText('Cleanup controls')).toBeNull();
  fireEvent.click(screen.getByRole('tab', {name:'API access'}));
  expect(screen.getByLabelText('Administrator key')).toHaveValue('draft-key');
  await waitFor(() => expect(sessionStorage.getItem('depo:admin-tab')).toBe('access'));
});

test('header access navigation selects credentials in an already mounted Admin page', () => {
  render(<AdminPage />);
  fireEvent(window, new CustomEvent('depo:admin-section', {detail:'access'}));
  expect(screen.getByRole('tab', {name:'API access'})).toHaveAttribute('aria-selected','true');
  expect(screen.getByRole('tabpanel', {name:'API access'})).toBeVisible();
});

test('failed registry shows unavailable counts and agent summary uses the agent table catalog', async () => {
  API_METHODS.admin.registry.mockRejectedValueOnce(new Error('Registry unavailable'));
  render(<AdminPage />);
  await screen.findByText('Registry unavailable');
  expect(screen.getByTestId('count-Services')).toHaveTextContent('—');
  await waitFor(() => expect(screen.getByTestId('count-Agents')).toHaveTextContent('0'));
});
