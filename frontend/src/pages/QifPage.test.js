import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('../services/apiClient', () => ({ qifAPI }));
vi.mock('../widgets/PageHeader', () => ({ default: ({ title }) => <h2>{title}</h2> }));
vi.mock('../widgets/KpiStrip', () => ({ default: () => null }));
vi.mock('../ui/IxIcons', () => ({
  CheckCircle2: () => null, Loader2: () => null, RefreshCw: () => null,
  Upload: () => null, Workflow: () => null, X: () => null,
}));

import QifPage from './QifPage';

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
  await waitFor(() => expect(qifAPI.startReferenceTask).toHaveBeenCalledWith(expect.objectContaining({ prefix: 'qif' })));
  await screen.findByText(/approve and publish ontology/i);
});

test('sanitizes the ontology prefix before submitting a task', async () => {
  render(<QifPage workflowMode />);
  const prefix = await screen.findByLabelText(/^prefix$/i);
  fireEvent.change(prefix, { target: { value: 'qif invalid!' } });
  expect(prefix).toHaveValue('qifinvalid');
});

test('renders task artifact links through the QIF API helper', async () => {
  qifAPI.getTask.mockResolvedValue({
    data: {
      ...task,
      summary: { files_processed: 1, classes_created: 1, properties_created: 1, references_found: 0 },
      artifacts: [{ name: 'qif_ontology.ttl', path: 'ontology/qif_ontology.ttl', kind: 'ontology' }],
    },
  });
  qifAPI.artifactUrl.mockReturnValue('http://127.0.0.1:8000/api/v1/qif/tasks/test/artifacts/ontology/qif_ontology.ttl');

  render(<QifPage workflowMode />);
  const start = await screen.findByRole('button', { name: /start reference task/i });
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  const artifact = await screen.findByRole('link', { name: /qif_ontology\.ttl/i });
  expect(qifAPI.artifactUrl).toHaveBeenCalledWith(task.task_id, 'ontology/qif_ontology.ttl');
  expect(artifact).toHaveAttribute('href', expect.stringContaining('/artifacts/ontology/qif_ontology.ttl'));
});
