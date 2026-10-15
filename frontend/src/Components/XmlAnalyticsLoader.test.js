import React from 'react';
import { vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import XmlAnalyticsLoader from './XmlAnalyticsLoader';
import { apiClient, dataPipelineAPI } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { post: vi.fn() }, dataPipelineAPI: { definitions: vi.fn(), runDefinition: vi.fn(), getRun: vi.fn(), reconcileAnalytics: vi.fn() } }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: () => 'test-token' }));
vi.mock('../config', () => ({ buildSemanticServiceUrl: (_service, path) => path }));
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });

test('only approved XML jobs are selectable and submission uses retained references', async () => {
  dataPipelineAPI.definitions.mockResolvedValue({ data: { definitions: [
    { job_id: 'load', version: '1.0.0', name: 'XML load', job_type: 'xml-analytics-materialize', lifecycle_state: 'approved', enabled: true },
    { job_id: 'draft', version: '1.0.0', name: 'Unapproved', job_type: 'xml-analytics-materialize', lifecycle_state: 'draft', enabled: true },
  ] } });
  dataPipelineAPI.runDefinition.mockResolvedValue({ data: { status: 'queued', run_manifest: { run_id: 'run-xml' } } });
  render(<XmlAnalyticsLoader />);
  fireEvent.click(screen.getByText('Load approved XML jobs'));
  await screen.findByText('XML load (1.0.0)');
  expect(screen.queryByText('Unapproved (1.0.0)')).toBeNull();
  fireEvent.change(screen.getByLabelText('Approved XML job'), { target: { value: 'load:1.0.0' } });
  fireEvent.change(screen.getByLabelText('Retained XSD artifact ID'), { target: { value: 'sha256:xsd' } });
  fireEvent.change(screen.getByLabelText('Retained XML artifact ID'), { target: { value: 'sha256:xml' } });
  fireEvent.change(screen.getByLabelText('Execution identity'), { target: { value: 'steward' } });
  fireEvent.click(screen.getByText('Validate and load XML'));
  await screen.findByRole('link', { name: 'View load run and evidence' });
  expect(screen.getByRole('link', { name: 'View load run and evidence' })).toHaveAttribute('href', '#/data-flow/run-xml');
  expect(dataPipelineAPI.runDefinition).toHaveBeenCalledWith('load', '1.0.0', expect.objectContaining({ schema_artifact_id: 'sha256:xsd', xml_artifact_id: 'sha256:xml', business_views: [] }), { approved_by: 'steward', approval_token: 'test-token' });
  for (const label of ['Schema dependencies (relative path → artifact ID, JSON)', 'Explicit business views (JSON, optional)']) {
    fireEvent.click(screen.getByText('Prepare another analytics task'));
    fireEvent.change(screen.getByLabelText(label), { target: { value: label.startsWith('Schema') ? '{"other.xsd":"sha256:dep"}' : '[] ' } });
    expect(screen.queryByRole('link', { name: 'View load run and evidence' })).toBeNull();
    fireEvent.click(screen.getByText('Validate and load XML'));
    await screen.findByRole('link', { name: 'View load run and evidence' });
  }
});

test('XML upload supplies its retained artifact identity without marking validation complete', async () => {
  apiClient.post.mockResolvedValue({ data: { artifact: { artifact_id: 'sha256:retained' }, instance_validation: 'not_performed' } });
  render(<XmlAnalyticsLoader />);
  fireEvent.change(screen.getByLabelText('XML instance file'), { target: { files: [new File(['<Root/>'], 'instance.xml')] } });
  fireEvent.click(screen.getByText('Retain XML instance'));
  await waitFor(() => expect(screen.getByLabelText('Retained XML artifact ID')).toHaveValue('sha256:retained'));
  expect(apiClient.post.mock.calls[0][0]).toBe('/api/v1/analytics/xml-artifacts');
  expect(dataPipelineAPI.runDefinition).not.toHaveBeenCalled();
});

async function prepareSubmission() {
  dataPipelineAPI.definitions.mockResolvedValue({ data: { definitions: [{ job_id: 'load', version: '1.0.0', name: 'XML load', job_type: 'xml-analytics-materialize', lifecycle_state: 'approved', enabled: true }] } });
  const view = render(<XmlAnalyticsLoader />);
  fireEvent.click(screen.getByText('Load approved XML jobs'));
  await screen.findByText('XML load (1.0.0)');
  fireEvent.change(screen.getByLabelText('Approved XML job'), { target: { value: 'load:1.0.0' } });
  fireEvent.change(screen.getByLabelText('Retained XSD artifact ID'), { target: { value: 'sha256:xsd' } });
  fireEvent.change(screen.getByLabelText('Retained XML artifact ID'), { target: { value: 'sha256:xml' } });
  fireEvent.change(screen.getByLabelText('Execution identity'), { target: { value: 'steward' } });
  return view;
}

test('unknown submission survives remount and must be reconciled before retrying', async () => {
  dataPipelineAPI.runDefinition.mockRejectedValue(new Error('network timeout'));
  const view = await prepareSubmission();
  fireEvent.click(screen.getByText('Validate and load XML'));
  await screen.findByText('Submission is unconfirmed. Check Data Flow history before retrying.');
  expect(screen.getByText('Validate and load XML')).toBeDisabled();
  expect(dataPipelineAPI.runDefinition).toHaveBeenCalledTimes(1);
  view.unmount();
  render(<XmlAnalyticsLoader />);
  expect(screen.getByLabelText('Retained analytics run ID')).toBeInTheDocument();
  dataPipelineAPI.getRun.mockResolvedValue({ data: { run_id: 'retained-run', status: 'failed' } });
  fireEvent.change(screen.getByLabelText('Retained analytics run ID'), { target: { value: 'retained-run' } });
  fireEvent.click(screen.getByText('Find retained analytics run'));
  await screen.findByText('Retained run: retained-run');
  expect(dataPipelineAPI.getRun).toHaveBeenCalledWith('retained-run');
  expect(dataPipelineAPI.runDefinition).toHaveBeenCalledTimes(1);
});

test('a server error run ID leads to evidence recovery without resubmitting XML', async () => {
  dataPipelineAPI.runDefinition.mockRejectedValue({ response: { status: 422, headers: { 'x-depo-run-id': 'committed-run' } } });
  await prepareSubmission();
  fireEvent.click(screen.getByText('Validate and load XML'));
  await screen.findByText('Retained run: committed-run');
  dataPipelineAPI.getRun.mockResolvedValue({ data: { run_id: 'committed-run', status: 'completed', output_manifest: { evidence_status: 'pending', load_status: 'completed' } } });
  fireEvent.click(screen.getByText('Refresh analytics run'));
  await screen.findByText('Rebuild analytics evidence');
  // Editing the approver must not hide recovery for the retained run.
  fireEvent.change(screen.getByLabelText('Execution identity'), { target: { value: 'recoverer' } });
  dataPipelineAPI.reconcileAnalytics.mockResolvedValue({ data: { status: 'completed', evidence_status: 'available', run_manifest: { run_id: 'committed-run', status: 'completed', output_manifest: { evidence_status: 'available' } } } });
  fireEvent.click(screen.getByText('Rebuild analytics evidence'));
  await waitFor(() => expect(screen.queryByText('Rebuild analytics evidence')).toBeNull());
  expect(dataPipelineAPI.reconcileAnalytics).toHaveBeenCalledWith('committed-run', { approved_by: 'recoverer', approval_token: 'test-token' });
  expect(dataPipelineAPI.runDefinition).toHaveBeenCalledTimes(1);
});

test('a rejected request without a retained run may be corrected and resubmitted', async () => {
  dataPipelineAPI.runDefinition.mockRejectedValue({ message: 'Denied', response: { status: 403, headers: {} } });
  await prepareSubmission();
  fireEvent.click(screen.getByText('Validate and load XML'));
  await screen.findByRole('alert');
  await waitFor(() => expect(screen.getByText('Validate and load XML')).not.toBeDisabled());
  expect(screen.queryByLabelText('Retained analytics task')).toBeNull();
});

test('an unknown submission can be released only after checking history', async () => {
  dataPipelineAPI.runDefinition.mockRejectedValue(new Error('network timeout'));
  await prepareSubmission();
  fireEvent.click(screen.getByText('Validate and load XML'));
  await screen.findByText('Submission is unconfirmed. Check Data Flow history before retrying.');
  expect(screen.getByText('Prepare another analytics task')).toBeDisabled();
  fireEvent.click(screen.getByLabelText('I checked history and no matching run exists'));
  fireEvent.click(screen.getByText('Prepare another analytics task'));
  expect(screen.getByText('Validate and load XML')).not.toBeDisabled();
  expect(dataPipelineAPI.runDefinition).toHaveBeenCalledTimes(1);
});
