import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import SemanticBridgeJobs from './SemanticBridgeJobs';

const preview = { job_id: 'preview-1', publication_job_id: 'publish-1', kind: 'preview', ontology_id: 'ontology', import_task_id: 'import', candidates: [
  { candidate_id: 'valid', source_term: 'part', ontology_term: 'Part', eligible: true },
  { candidate_id: 'invalid', source_term: 'bad', ontology_term: 'Unknown', eligible: false },
] };
let api;
beforeEach(() => {
  sessionStorage.clear();
  api = { preview: vi.fn().mockResolvedValue({ data: preview }), status: vi.fn(), publish: vi.fn().mockResolvedValue({ data: { job_id: 'publish-1', status: 'published', receipt: { applied_links: 1, approved_by: 'reviewer' } } }) };
});
afterEach(cleanup);
const mount = () => render(<SemanticBridgeJobs ontologyId="ontology" importTaskId="import" api={api} />);
async function create() { fireEvent.click(screen.getByText('Create preview')); await screen.findByLabelText('Approve part to Part'); }

test('requires explicit eligible selection and review confirmation', async () => {
  mount(); await create();
  expect(screen.getByLabelText('Approve part to Part')).not.toBeChecked();
  expect(screen.getByLabelText('Approve bad to Unknown')).toBeDisabled();
  expect(screen.getByText('Publish approved mappings')).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Approve part to Part'));
  expect(screen.getByText('Publish approved mappings')).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm reviewed mappings'));
  fireEvent.click(screen.getByText('Publish approved mappings'));
  await screen.findByText('Publication: published');
  expect(api.publish).toHaveBeenCalledWith('preview-1', ['valid'], { approved_by: '', approval_token: '' });
});

test('response loss freezes selection and preserves same publication retry', async () => {
  api.publish.mockRejectedValueOnce(new Error('network'));
  mount(); await create();
  fireEvent.click(screen.getByLabelText('Approve part to Part'));
  fireEvent.click(screen.getByLabelText('Confirm reviewed mappings'));
  fireEvent.click(screen.getByText('Publish approved mappings'));
  await screen.findByRole('alert');
  expect(screen.getByLabelText('Approve part to Part')).toBeDisabled();
  fireEvent.click(screen.getByText('Retry same publication'));
  await screen.findByText('Publication: published');
  expect(api.publish).toHaveBeenCalledTimes(2);
  expect(api.publish.mock.calls[0][1]).toEqual(api.publish.mock.calls[1][1]);
});

test('resume restores publication selection and status', async () => {
  api.status.mockResolvedValueOnce({ data: preview }).mockResolvedValueOnce({ data: { job_id: 'publish-1', status: 'published', approved_ids: ['valid'] } });
  mount();
  fireEvent.change(screen.getByLabelText('Saved preview ID'), { target: { value: 'preview-1' } });
  fireEvent.click(screen.getByText('Load preview'));
  await screen.findByText('Publication: published');
  expect(screen.getByLabelText('Approve part to Part')).toBeChecked();
  expect(screen.getByLabelText('Approve part to Part')).toBeDisabled();
});

test('changing inputs discards old preview and credentials are not persisted', async () => {
  const view = mount();
  fireEvent.change(screen.getByLabelText('Approval token'), { target: { value: 'secret-test-value' } });
  await create();
  expect(JSON.stringify(sessionStorage)).not.toContain('secret-test-value');
  view.rerender(<SemanticBridgeJobs ontologyId="other" importTaskId="import" api={api} />);
  await waitFor(() => expect(screen.queryByLabelText('Approve part to Part')).toBeNull());
  expect(screen.getByLabelText('Approval token')).toHaveValue('');
});
