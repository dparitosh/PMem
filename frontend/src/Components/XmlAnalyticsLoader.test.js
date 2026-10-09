import React from 'react';
import { vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import XmlAnalyticsLoader from './XmlAnalyticsLoader';
import { apiClient, dataPipelineAPI } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ apiClient: { post: vi.fn() }, dataPipelineAPI: { definitions: vi.fn(), runDefinition: vi.fn() } }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: () => 'test-token' }));
vi.mock('../config', () => ({ buildSemanticServiceUrl: (_service, path) => path }));
beforeEach(() => vi.clearAllMocks());

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
  expect(dataPipelineAPI.runDefinition).toHaveBeenCalledWith('load', '1.0.0', expect.objectContaining({ schema_artifact_id: 'sha256:xsd', xml_artifact_id: 'sha256:xml', business_views: [] }), { approved_by: 'steward', approval_token: 'test-token' });
  for (const label of ['Schema dependencies (relative path → artifact ID, JSON)', 'Explicit business views (JSON, optional)']) {
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
