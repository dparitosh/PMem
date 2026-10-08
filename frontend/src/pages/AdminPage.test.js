import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import AdminPage from './AdminPage';

vi.mock('../Components/CredentialSettings', () => ({ default: () => <label>Administrator key<input aria-label="Administrator key" /></label> }));
vi.mock('../Components/AdminPanel', () => ({ default: () => <div>Cleanup controls</div> }));
vi.mock('../Components/AgentControlPanel', () => ({ default: () => <div>Workflow controls</div> }));
vi.mock('../Components/AgentProposalPanel', () => ({ default: () => <div>Agent recommendations</div> }));
vi.mock('../Components/ServiceIntegrationPanel', () => ({ default: () => <div>Integration health</div> }));
vi.mock('../widgets/RegistryWidget', () => ({ default: ({ title }) => <div>{title}</div> }));
vi.mock('../widgets/KpiStrip', () => ({ default: () => <div>Summary counts</div> }));
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
