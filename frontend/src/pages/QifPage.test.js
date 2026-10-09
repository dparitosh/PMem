import { setCredentialProfile, getCredentialProfile } from '../services/serviceAuth';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

const { qifAPI } = vi.hoisted(() => ({ qifAPI: {
  catalog: vi.fn(),
  agents: vi.fn(),
  listTasks: vi.fn(),
  startReferenceTask: vi.fn(),
  startUploadTask: vi.fn(),
  getTask: vi.fn(),
  commit: vi.fn(),
  cancel: vi.fn(),
  retryGraph: vi.fn(),
  artifactUrl: vi.fn(),
} }));

const apiClient = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../services/apiClient', () => ({ qifAPI, apiClient }));
vi.mock('../contexts/OntologyContext', () => ({ useOntologies: () => ({ ontologies: [], loading: false, error: '', fetchOntologies: vi.fn() }) }));
vi.mock('../widgets/PageHeader', () => ({ default: ({ title }) => <h2>{title}</h2> }));
vi.mock('../widgets/KpiStrip', () => ({ default: () => null }));
vi.mock('../ui/IxIcons', () => ({
  CheckCircle2: () => null, Loader2: () => null, RefreshCw: () => null,
  Upload: () => null, Workflow: () => null, X: () => null,
}));

import QifPage from './QifPage';

test('history selection is disabled while a task cancellation is pending', async () => {
  const other = { ...task, task_id: 'b'.repeat(32), ontology_name: 'Other task' };
  qifAPI.listTasks.mockResolvedValue({ data: { tasks: [task, other] } });
  let finish;
  qifAPI.cancel.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<QifPage workflowMode />);
  await screen.findByRole('button', { name: /approve and publish ontology/i });
  fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
  expect(screen.getByRole('button', { name: /open qif task Other task/i })).toBeDisabled();
  await act(async () => finish({ data: { ...task, status: 'cancelled' } }));
  await waitFor(() => expect(screen.getByRole('button', { name: /open qif task Other task/i })).toBeEnabled());
});

const task = {
  task_id: 'a'.repeat(32), source: 'bundled_reference', ontology_name: 'QIF 3.0 Ontology', prefix: 'qif', description: '',
  status: 'awaiting_approval', stage: 'review', progress: 80, created_at: '2026-08-31T00:00:00Z', updated_at: '2026-08-31T00:00:00Z',
  source_files: ['QIFDocument.xsd'], events: [], validation: null, summary: null, artifacts: [], graph_sync: { status: 'not_started' },
};

beforeEach(() => {
  vi.clearAllMocks();
  qifAPI.catalog.mockResolvedValue({ data: { file_count: 2, files: [{ name: 'QIFDocument.xsd', area: 'application' }] } });
  qifAPI.agents.mockResolvedValue({ data: { agents: [] } });
  qifAPI.listTasks.mockResolvedValue({ data: { tasks: [] } });
  qifAPI.getTask.mockResolvedValue({ data: task });
  qifAPI.startReferenceTask.mockResolvedValue({ data: { task_id: task.task_id } });
});

test('starts a reference task with accessible metadata controls', async () => {
  render(<QifPage workflowMode />);
  const start = await screen.findByRole('button', { name: /start reference task/i });
  await waitFor(() => expect(start).toBeEnabled());
  expect(screen.getByLabelText(/ontology name/i)).toHaveValue('QIF 3.0 Ontology');
  expect(screen.getByLabelText(/select qif xsd files/i)).toHaveAttribute('multiple');

  fireEvent.click(start);
  await waitFor(() => expect(qifAPI.startReferenceTask).toHaveBeenCalledWith(expect.objectContaining({ prefix: 'qif' }), {}));
  await screen.findByText(/approve and publish ontology/i);
});

test('sanitizes the ontology prefix before submitting a task', async () => {
  render(<QifPage workflowMode />);
  const prefix = await screen.findByLabelText(/^prefix$/i);
  fireEvent.change(prefix, { target: { value: 'qif invalid!' } });
  expect(prefix).toHaveValue('qifinvalid');
});

test('uses a scoped ontology write key for actions', async () => {
  render(<QifPage workflowMode />);
  const start = await screen.findByRole('button', { name: /start reference task/i });
  await waitFor(() => expect(start).toBeEnabled());
  setCredentialProfile('ONTOLOGY_APPROVAL_TOKEN', 'write-only-key');
  fireEvent.click(start);
  await waitFor(() => expect(qifAPI.startReferenceTask).toHaveBeenCalledWith(expect.any(Object), { headers: { Authorization: 'Bearer write-only-key' } }));
  const publish = await screen.findByRole('button', { name: /approve and publish ontology/i });
  await waitFor(() => expect(publish).toBeEnabled());
  fireEvent.click(publish);
  await waitFor(() => expect(qifAPI.commit).toHaveBeenCalledWith(task.task_id, { headers: { Authorization: 'Bearer write-only-key' } }));
});

test('ignores an older task response after another task is selected', async () => {
  const other = { ...task, task_id: 'b'.repeat(32), ontology_name: 'Other ontology' };
  let resolveOther;
  qifAPI.listTasks.mockResolvedValue({ data: { tasks: [task, other] } });
  qifAPI.getTask.mockImplementation(id => id === other.task_id
    ? new Promise(resolve => { resolveOther = resolve; }) : Promise.resolve({ data: task }));
  render(<QifPage workflowMode />);
  const a = await screen.findByRole('button', { name: /Open QIF task QIF 3.0 Ontology/ });
  const b = await screen.findByRole('button', { name: /Open QIF task Other ontology/ });
  await waitFor(() => expect(a).toHaveAttribute('aria-pressed', 'true'));
  fireEvent.click(b);
  fireEvent.click(a);
  await waitFor(() => expect(a).toHaveAttribute('aria-pressed', 'true'));
  await act(async () => { resolveOther({ data: other }); });
  expect(a).toHaveAttribute('aria-pressed', 'true');
  expect(b).toHaveAttribute('aria-pressed', 'false');
});

test('downloads task artifacts through the authenticated QIF API helper', async () => {
  qifAPI.getTask.mockResolvedValue({
    data: {
      ...task,
      summary: { files_processed: 1, classes_created: 1, properties_created: 1, references_found: 0 },
      artifacts: [{ name: 'qif_ontology.ttl', path: 'ontology/qif_ontology.ttl', kind: 'ontology' }],
    },
  });
  qifAPI.artifactUrl.mockReturnValue('http://127.0.0.1:8010/api/v1/qif/tasks/test/artifacts/ontology/qif_ontology.ttl');

  render(<QifPage workflowMode />);
  const start = await screen.findByRole('button', { name: /start reference task/i });
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  const artifact = await screen.findByRole('button', { name: /qif_ontology\.ttl/i });
  apiClient.get.mockResolvedValue({ data: new Blob(['ontology']) });
  const createUrl = vi.fn(() => 'blob:fixture');
  vi.stubGlobal('URL', Object.assign(URL, {createObjectURL:createUrl, revokeObjectURL:vi.fn()}));
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  fireEvent.click(artifact);
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith(expect.stringContaining('/artifacts/ontology/qif_ontology.ttl'), {responseType:'blob'}));
  await waitFor(() => expect(createUrl).toHaveBeenCalled());
  click.mockRestore(); vi.unstubAllGlobals();
  expect(qifAPI.artifactUrl).toHaveBeenCalledWith(task.task_id, 'ontology/qif_ontology.ttl');
});
