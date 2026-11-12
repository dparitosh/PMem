import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import AdminPage from './AdminPage';
import { API_METHODS } from '../services/apiClient';
import agenticAPI from '../services/agenticApi';

vi.mock('@siemens/ix-react', () => import('../ui/ix/ixReact.mock.js'));
vi.mock('../Components/CredentialSettings', () => ({ default: () => <label>Administrator key<input aria-label="Administrator key" /></label> }));
vi.mock('../Components/AdminPanel', () => ({ default: () => <div>Cleanup controls</div> }));
vi.mock('../Components/AgentControlPanel', () => ({ default: () => <div>Workflow controls</div> }));
vi.mock('../Components/AgentProposalPanel', () => ({ default: () => <div>Agent recommendations</div> }));
vi.mock('../Components/ServiceIntegrationPanel', () => ({ default: () => <div>Integration health</div> }));
vi.mock('../widgets/RegistryWidget', () => ({ default: ({ title, rows = [], columns = [] }) => <div>{title}{columns.map(c => <span key={c.field}>{c.headerName || c.field}</span>)}{rows.map(r => <span key={r.id}>{r.description} {r.registration_status}</span>)}</div> }));
vi.mock('../widgets/KpiStrip', () => ({ default: ({ items }) => <div>{items.map(item => <span key={item.label} data-testid={`count-${item.label}`}>{item.value ?? '—'}</span>)}</div> }));
vi.mock('../services/apiClient', () => ({ API_METHODS: {admin:{registry:vi.fn(async () => ({data:{}}))}} }));
vi.mock('../services/agenticApi', () => ({default:{isEnabled:()=>true,isConfigured:()=>true,registry:vi.fn()}}));
const registryResponse = (agents = []) => ({data:{agents,tools:[],workflows:[],registry:{schema_version:1,revision:'a'.repeat(64),agent_count:agents.length,tool_count:0,workflow_count:0,source:'validated deployment catalog',readiness:'not_verified'}}});
beforeEach(() => { window.history.replaceState(null,'','#/admin');sessionStorage.clear(); agenticAPI.registry.mockReset(); agenticAPI.registry.mockResolvedValue(registryResponse()); });

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

test('Agent Registry exposes responsibility and readiness without treating registration as health', async () => {
  agenticAPI.registry.mockResolvedValue(registryResponse([{id:'ontology-steward',description:'Review mappings for ambiguity',registration_status:'registered; live dependencies unverified'}]));
  render(<AdminPage />);
  fireEvent.click(screen.getByRole('tab', {name:'Agents & workflows'}));
  const panel = within(screen.getByRole('tabpanel', {name:'Agents & workflows'}));
  expect(panel.getByText('Agent Registry')).toBeVisible();
  expect(await panel.findByText(/Review mappings for ambiguity/)).toBeVisible();
  expect(panel.getByText('Responsibility')).toBeVisible();
  expect(panel.getByText(/Readiness: not verified/)).toBeVisible();
  expect(screen.getByTestId('count-Agents')).toHaveTextContent('1');
});

test('malformed registry is unavailable rather than an empty successful list', async () => {
  agenticAPI.registry.mockResolvedValue({data:{agents:[],tools:[]}});
  render(<AdminPage />);
  await screen.findByText(/Agent registry response is incomplete/);
  expect(screen.getByTestId('count-Agents')).toHaveTextContent('—');
});

test.each([
  ['null agent', data => { data.agents = [null]; data.registry.agent_count = 1; }],
  ['duplicate agent', data => { data.agents = [{id:'same'}, {id:'same'}]; data.registry.agent_count = 2; }],
  ['invalid tool', data => { data.tools = [{}]; data.registry.tool_count = 1; }],
  ['missing workflows', data => { delete data.workflows; }],
  ['workflow count mismatch', data => { data.registry.workflow_count = 1; }],
])('rejects registry with %s', async (_name, corrupt) => {
  const response = registryResponse();
  corrupt(response.data);
  agenticAPI.registry.mockResolvedValue(response);
  render(<AdminPage />);
  await screen.findByText(/Agent registry response is incomplete/);
  expect(screen.getByTestId('count-Agents')).toHaveTextContent('—');
});

test('late registry from a replaced credential session cannot overwrite the current registry', async () => {
  let resolveOld;
  agenticAPI.registry.mockImplementationOnce(() => new Promise(resolve => {resolveOld=resolve;}));
  render(<AdminPage />);
  fireEvent(window, new CustomEvent('depo:credentials-changed'));
  await waitFor(() => expect(screen.getByTestId('count-Agents')).toHaveTextContent('0'));
  await act(async () => resolveOld(registryResponse([{id:'old',description:'Old session data'}])));
  expect(screen.getByTestId('count-Agents')).toHaveTextContent('0');
  expect(screen.queryByText(/Old session data/)).toBeNull();
});

test('reconnect clears already displayed registry data before loading the next session', async () => {
  agenticAPI.registry.mockResolvedValueOnce(registryResponse([{id:'old',description:'Previous session registry'}]));
  render(<AdminPage />);
  fireEvent.click(screen.getByRole('tab', {name:'Agents & workflows'}));
  await screen.findByText(/Previous session registry/);
  agenticAPI.registry.mockImplementationOnce(() => new Promise(() => {}));
  fireEvent(window, new CustomEvent('depo:credentials-changed'));
  expect(screen.queryByText(/Previous session registry/)).toBeNull();
  expect(screen.getByText('Loading registered agents…')).toBeVisible();
  expect(screen.getByTestId('count-Agents')).toHaveTextContent('—');
});

test('Admin deep link overrides legacy storage and follows history',async()=>{
 sessionStorage.setItem('depo:admin-tab','overview');window.history.replaceState(null,'','#/admin?view=maintenance');
 render(<AdminPage/>);expect(screen.getByRole('tabpanel',{name:'Maintenance'})).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'API access'}));expect(window.location.hash).toContain('view=access');
 await act(async()=>{window.history.replaceState(null,'','#/admin?view=maintenance');window.dispatchEvent(new PopStateEvent('popstate'));});
 expect(screen.getByRole('tabpanel',{name:'Maintenance'})).toBeVisible();
});
