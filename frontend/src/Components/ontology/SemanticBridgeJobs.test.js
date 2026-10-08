import { setCredentialProfile, getCredentialProfile } from '../../services/serviceAuth';
import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import SemanticBridgeJobs from './SemanticBridgeJobs';
import agenticAPI from '../../services/agenticApi';

const preview = { job_id: 'preview-1', publication_job_id: 'publish-1', kind: 'preview', ontology_id: 'ontology', import_task_id: 'import', candidates: [
  { candidate_id: 'valid', source_term: 'part', ontology_term: 'Part', eligible: true },
  { candidate_id: 'invalid', source_term: 'bad', ontology_term: 'Unknown', eligible: false },
] };
let api;
beforeEach(() => {
  sessionStorage.clear();
  setCredentialProfile('AGENTIC_APPROVAL_TOKEN', 'supervisor');
  api = { preview: vi.fn().mockResolvedValue({ data: preview }), status: vi.fn(), publish: vi.fn().mockResolvedValue({ data: { job_id: 'publish-1', status: 'published', receipt: { applied_links: 1, approved_by: 'reviewer' } } }) };
});
afterEach(cleanup);
const mount = () => {
  const view = render(<SemanticBridgeJobs ontologyId="ontology" importTaskId="import" api={api} />);
  fireEvent.change(screen.getByLabelText('Approver'), {target: {value: 'reviewer'}});
  return view;
};
async function create() { fireEvent.click(screen.getByText('Create preview')); await screen.findByLabelText('Approve part to Part'); }

test('saves manual drafts as visible recommendations without selecting publication', async () => {
  const manual = [{ source_term: 'part', source_type: 'Entity', target_term: 'Part', target_ontology_type: 'Class' }];
  api.preview.mockResolvedValue({ data: { ...preview, agent_run_id: 'agent-run-1',
    recommendation_summary: { total: 2, eligible: 1 }, candidates: [
      { ...preview.candidates[0], evidence: ['server-resolved source and target'] }, preview.candidates[1],
    ] } });
  render(<SemanticBridgeJobs ontologyId="ontology" importTaskId="import" manualMappings={manual} api={api} />);
  fireEvent.change(screen.getByLabelText('Approver'), { target: { value: 'reviewer' } });
  await create();
  expect(api.preview).toHaveBeenCalledWith('ontology', 'import', { approved_by: 'reviewer', approval_token: 'supervisor' }, manual);
  expect(screen.getByText(/2 mapping recommendations; 1 eligible/)).toBeInTheDocument();
  expect(screen.getByText('server-resolved source and target')).toBeInTheDocument();
  expect(screen.getByText('Preview agent run: agent-run-1')).toBeInTheDocument();
  expect(screen.getByLabelText('Approve part to Part')).not.toBeChecked();
  expect(api.publish).not.toHaveBeenCalled();
});

test('structured validation errors do not crash or echo submitted credentials', async () => {
  api.preview.mockRejectedValue({ response: { status: 422, data: { detail: [{ msg: 'invalid', input: 'private-credential' }] } } });
  mount(); fireEvent.click(screen.getByText('Create preview'));
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid request');
  expect(document.body.textContent).not.toContain('private-credential');
});

test('malformed saved preview is rejected without rendering a broken table', async () => {
  api.preview.mockResolvedValue({ data: { ...preview, candidates: null } });
  mount(); fireEvent.click(screen.getByText('Create preview'));
  expect(await screen.findByRole('alert')).toHaveTextContent('Saved preview is incomplete');
  expect(screen.queryByText('Publish approved mappings')).toBeNull();
});

test('credential changes discard recommendations and late responses', async () => {
  let resolve;
  api.preview.mockReturnValue(new Promise(done => { resolve = done; }));
  mount(); fireEvent.click(screen.getByText('Create preview'));
  fireEvent(window, new Event('depo:credentials-cleared'));
  resolve({ data: preview });
  await waitFor(() => expect(screen.getByText('Create preview')).not.toBeDisabled());
  expect(screen.queryByLabelText('Approve part to Part')).toBeNull();
});

test('failed publication recovery keeps selection locked until status is recovered', async () => {
  api.status.mockResolvedValueOnce({ data: preview }).mockRejectedValueOnce(new Error('network'))
    .mockResolvedValueOnce({ data: { job_id: 'publish-1', status: 'retryable', approved_ids: ['valid'] } });
  mount();
  fireEvent.change(screen.getByLabelText('Saved preview ID'), { target: { value: 'preview-1' } });
  fireEvent.click(screen.getByText('Load preview'));
  await screen.findByRole('alert');
  expect(screen.getByLabelText('Approve part to Part')).toBeDisabled();
  expect(screen.getByText('Retry same publication')).toBeDisabled();
  fireEvent.click(screen.getByText('Refresh publication status'));
  await screen.findByText('Publication: retryable');
  expect(screen.getByLabelText('Approve part to Part')).toBeChecked();
});

test('refresh of an absent publication unlocks review', async () => {
  api.status.mockResolvedValueOnce({ data: preview }).mockRejectedValueOnce(new Error('network'))
    .mockRejectedValueOnce({ response: { status: 404 } });
  mount();
  fireEvent.change(screen.getByLabelText('Saved preview ID'), { target: { value: 'preview-1' } });
  fireEvent.click(screen.getByText('Load preview'));
  await screen.findByRole('alert');
  fireEvent.click(screen.getByText('Refresh publication status'));
  await screen.findByText('No publication exists yet. Select and review mappings before publishing.');
  expect(screen.getByLabelText('Approve part to Part')).not.toBeDisabled();
  expect(screen.getByText('Publish approved mappings')).toBeDisabled();
});

test('wrong-source preview explains how to recover', async () => {
  api.status.mockResolvedValueOnce({ data: { ...preview, ontology_id: 'different' } });
  mount();
  fireEvent.change(screen.getByLabelText('Saved preview ID'), { target: { value: 'preview-1' } });
  fireEvent.click(screen.getByText('Load preview'));
  expect(await screen.findByRole('alert')).toHaveTextContent('Preview belongs to another source or ontology');
  expect(screen.queryByLabelText('Approve part to Part')).toBeNull();
});

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
  expect(api.publish).toHaveBeenCalledWith('preview-1', ['valid'], { approved_by: 'reviewer', approval_token: 'supervisor' });
});

test('response loss freezes selection and preserves same publication retry', async () => {
  api.publish.mockRejectedValueOnce(new Error('network'));
  api.status.mockResolvedValueOnce({data: {job_id: 'publish-1', status: 'retryable', approved_ids: ['valid']}});
  mount(); await create();
  fireEvent.click(screen.getByLabelText('Approve part to Part'));
  fireEvent.click(screen.getByLabelText('Confirm reviewed mappings'));
  fireEvent.click(screen.getByText('Publish approved mappings'));
  await screen.findByRole('alert');
  expect(screen.getByLabelText('Approve part to Part')).toBeDisabled();
  expect(screen.getByText('Retry same publication')).toBeDisabled();
  fireEvent.click(screen.getByText('Refresh publication status'));
  await screen.findByText('Publication: retryable');
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
  setCredentialProfile('AGENTIC_APPROVAL_TOKEN', 'secret-test-value');
  await create();
  expect(JSON.stringify(sessionStorage)).not.toContain('secret-test-value');
  view.rerender(<SemanticBridgeJobs ontologyId="other" importTaskId="import" api={api} />);
  await waitFor(() => expect(screen.queryByLabelText('Approve part to Part')).toBeNull());
  expect(screen.queryByLabelText('Approval token')).toBeNull();
});


test('ontology review displays structured evidence citations and limitations', async () => {
  const configured=vi.spyOn(agenticAPI,'isConfigured').mockReturnValue(true);
  const review=vi.spyOn(agenticAPI,'orchestrateOntology').mockResolvedValue({data:{steps:[{result:{llm:{enabled:true,text:'Review only',review:{questions:[{question:'Is the domain compatible?',evidence_iris:['urn:Part']}],limitations:'No formal reasoner was run.'}}}}]}});
  try {
    mount();
    fireEvent.click(screen.getByText('Run ontology agent review'));
    await screen.findByText('Evidence IRIs: urn:Part');
    expect(screen.getByText('Limitations: No formal reasoner was run.')).toBeVisible();
    expect(api.publish).not.toHaveBeenCalled();
  } finally {configured.mockRestore();review.mockRestore();}
});
