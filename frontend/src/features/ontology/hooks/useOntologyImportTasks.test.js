import React from 'react';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import useOntologyImportTasks from './useOntologyImportTasks';
const api = vi.hoisted(() => ({ getTasks: vi.fn(), getStatus: vi.fn(), getPreview: vi.fn() }));
vi.mock('../../../services/apiClient', () => ({ API_METHODS: { import: api } }));
function Workspace() {
  const state = useOntologyImportTasks();
  return <><select aria-label="Task" value={state.selectedImportTaskId} onChange={event => state.setSelectedImportTaskId(event.target.value)}>
    {state.importTasks.map(task => <option key={task.task_id} value={task.task_id}>{task.task_id}</option>)}
  </select><button onClick={state.refreshImportTasks}>Refresh</button><output>{state.selectedImportTaskDetails?.name || 'No details'}</output><output>{state.selectedImportTaskPreview?.name || 'No preview'}</output></>;
}
beforeEach(() => {
  vi.resetAllMocks();
  api.getTasks.mockResolvedValue({ data: { tasks: [{ task_id: 'A' }, { task_id: 'B' }] } });
  api.getStatus.mockResolvedValue({ data: { name: 'Details A' } });
  api.getPreview.mockResolvedValue({ data: { name: 'Preview A' } });
});
test('manual refresh replaces a removed selection with an available task', async () => {
  render(<Workspace />);
  await screen.findByText('Preview A');
  api.getTasks.mockResolvedValue({data:{tasks:[{task_id:'B'}]}});
  fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
  await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('B'));
  expect(screen.queryByRole('option',{name:'A'})).not.toBeInTheDocument();
});
test('selection clears old evidence immediately without reloading the task registry', async () => {
  render(<Workspace />);
  await screen.findByText('Preview A');
  let resolveStatus, resolvePreview;
  api.getStatus.mockImplementation(() => new Promise(resolve => { resolveStatus = resolve; }));
  api.getPreview.mockImplementation(() => new Promise(resolve => { resolvePreview = resolve; }));
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'B' } });
  expect(screen.queryByText('Preview A')).not.toBeInTheDocument();
  expect(screen.queryByText('Details A')).not.toBeInTheDocument();
  expect(api.getTasks).toHaveBeenCalledTimes(1);
  await act(async () => { resolveStatus({ data: { name: 'Details B' } }); resolvePreview({ data: { name: 'Preview B' } }); });
  expect(await screen.findByText('Preview B')).toBeVisible();
});
test('late task reads are aborted and cannot replace the current selection', async () => {
  const pending = [];
  api.getStatus.mockImplementation((id, options) => new Promise(resolve => pending.push({ id, options, resolve })));
  api.getPreview.mockImplementation((id, options) => new Promise(resolve => pending.push({ id, options, resolve })));
  const view = render(<Workspace />);
  await waitFor(() => expect(pending).toHaveLength(2));
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'B' } });
  await waitFor(() => expect(pending).toHaveLength(4));
  expect(pending[0].options.signal.aborted).toBe(true);
  await act(async () => { pending.slice(2).forEach(read => read.resolve({ data: { name: 'Current B' } })); });
  await act(async () => { pending.slice(0, 2).forEach(read => read.resolve({ data: { name: 'Stale A' } })); });
  expect(screen.queryByText('Stale A')).not.toBeInTheDocument();
  view.unmount();
  expect(pending[2].options.signal.aborted).toBe(true);
});
test('credentials changes clear selected evidence and refresh the registry', async () => {
  render(<Workspace />);
  await screen.findByText('Preview A');
  api.getTasks.mockImplementation(() => new Promise(() => {}));
  act(() => window.dispatchEvent(new Event('depo:credentials-changed')));
  expect(screen.queryByText('Preview A')).not.toBeInTheDocument();
  await waitFor(() => expect(api.getTasks).toHaveBeenCalledTimes(2));
});

test('schema cleanup removes retained task choices and preview evidence', async () => {
  render(<Workspace />);
  await screen.findByText('Preview A');
  api.getTasks.mockResolvedValue({data:{tasks:[]}});
  act(() => window.dispatchEvent(new Event('dt-schema-cleaned')));
  await waitFor(() => expect(api.getTasks).toHaveBeenCalledTimes(2));
  expect(screen.queryByText('Preview A')).not.toBeInTheDocument();
  expect(screen.queryByRole('option',{name:'A'})).not.toBeInTheDocument();
});
