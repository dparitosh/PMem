import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import ReportsTab from './ReportsTab';
import { dataPipelineAPI } from '../services/apiClient';

vi.mock('../contexts/OntologyContext', () => ({ useOntologies: () => ({ ontologies: [] }) }));
vi.mock('../services/apiClient', () => ({ apiClient: { get: vi.fn(async()=>({data:{}})) }, dataPipelineAPI: { telemetry: vi.fn() } }));
vi.mock('../services/graphApi', () => ({ graphApi: { computationOptions:vi.fn(async()=>({data:{sources:[]}})),getMetrics:vi.fn(async()=>({data:{scope:{sampled:false,type:'published_rdf_projection',ontology_id:null},resources:0,relationships:0,classes:0}})),getOverview: vi.fn(async () => ({ data: { nodes: [], relationships: [] } })) } }));
vi.mock('./ReportsAnalytics', () => ({ default: ({ telemetry, telemetryError }) => <div>
  {telemetry ? `Recorded runs: ${telemetry.completed_runs}` : 'No current telemetry'}
  {telemetryError && <p>{telemetryError}</p>}
</div> }));

test('failed refresh clears previously displayed pipeline charts', async () => {
  dataPipelineAPI.telemetry.mockResolvedValueOnce({ data: { completed_runs: 8 } })
    .mockRejectedValueOnce(new Error('Telemetry offline'));
  render(<ReportsTab />);
  await screen.findByText('Recorded runs: 8');
  fireEvent(window, new Event('depo:credentials-changed'));
  await waitFor(() => expect(screen.queryByText('Recorded runs: 8')).toBeNull());
  expect(screen.getByText('No current telemetry')).toBeVisible();
});
