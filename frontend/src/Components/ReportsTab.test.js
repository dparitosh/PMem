import React from 'react';
import { vi } from 'vitest';
import { graphApi } from '../services/graphApi';
import { render, screen, waitFor, act } from '@testing-library/react';
import ReportsTab, { escapeCsv, normalizeReportNode } from './ReportsTab';

vi.mock('../contexts/OntologyContext', () => ({
  OntologyProvider: ({ children }) => children,
  useOntologies: () => ({
    ontologies: [],
    loading: false,
    error: null,
    lastUpdated: null,
    fetchOntologies: vi.fn(),
    getOntologyByPrefix: vi.fn(),
    getOntologyById: vi.fn(),
  }),
}));

import { OntologyProvider } from '../contexts/OntologyContext';

test('CSV quotes fields using doubled quotes and preserves real newlines', () => {
  expect(escapeCsv('Part "A", revision\n2')).toBe('"Part ""A"", revision\n2"');
  expect(escapeCsv(null)).toBe('""');
});

vi.mock('../services/graphApi', () => {
  const api={
    computationOptions: vi.fn(async()=>({data:{sources:[]}})),
    getOverview: vi.fn(async () => ({data:{nodes:[],links:[]}})),
    getOntologyGraph: vi.fn(async () => ({data:{nodes:[],links:[]}})),
    getOntologyReport: vi.fn(async ontology_id => ({data:{ontology_id,sampled:false,resources:0,outgoing_links:0,unmapped:0,categories:[],notes:[]}})),
    getMetrics: vi.fn(async () => ({data:{resources:1700,relationships:2400,classes:25,scope:{sampled:false,type:'published_rdf_projection',ontology_id:null}}})),
  };
  return {graphApi:api,default:api};
});

vi.mock('../services/apiClient', () => ({
  apiClient: { get: vi.fn(async () => ({ data: {} })) },
  dataPipelineAPI: { telemetry: vi.fn(async () => ({ data: {} })) },
}));

test('ReportsTab does not substitute canvas data for an empty report projection', async () => {
  render(
    <OntologyProvider>
      <ReportsTab
        searchResults={[]}
        graphData={{
          nodes: [
            {
              elementId: 'n1',
              labels: ['Part'],
              label: 'Part',
              properties: { name: 'Rotor', part_number: 'P-100' },
            },
          ],
          links: [],
        }}
      />
    </OntologyProvider>
  );

  await waitFor(() => expect(graphApi.getOverview).toHaveBeenCalled());
  expect(await screen.findByText('1700')).toBeVisible();
  expect(graphApi.getMetrics).toHaveBeenCalledWith('', expect.any(AbortSignal), '');
  expect(screen.queryByText('Rotor')).toBeNull();
  expect(screen.getByText('Analytics overview')).toBeInTheDocument();
  expect(screen.getByText('Entity distribution')).toBeInTheDocument();
  expect(screen.getByText('Relationship distribution')).toBeInTheDocument();
  expect(screen.getByText('Ontology coverage')).toBeInTheDocument();
  expect(screen.getByText('Data-job status')).toBeInTheDocument();
  expect(screen.getByText('Record quality metrics')).toBeInTheDocument();
});


test('engineering report retains the requested ontology across history navigation', async () => {
  const original=window.location.hash;
  graphApi.getOntologyGraph=vi.fn(async()=>({data:{nodes:[],links:[]}}));
  window.history.replaceState(null,'','#/reports?view=engineering&ontology_id=exact-source');
  const mounted=render(<ReportsTab searchResults={[]} graphData={{nodes:[],links:[]}}/>);
  try {
    expect(screen.getByLabelText('Report ontology')).toHaveValue('exact-source');
    await waitFor(()=>expect(graphApi.getOntologyGraph).toHaveBeenCalledWith('exact-source',1200,expect.any(AbortSignal)));
    act(()=>{window.history.replaceState(null,'','#/reports?view=engineering&ontology_id=other-source');window.dispatchEvent(new PopStateEvent('popstate'));});
    expect(screen.getByLabelText('Report ontology')).toHaveValue('other-source');
    await waitFor(()=>expect(graphApi.getOntologyGraph).toHaveBeenCalledWith('other-source',1200,expect.any(AbortSignal)));
  } finally {mounted.unmount();window.history.replaceState(null,'',original||'#/reports');}
});


test('engineering source selector includes published graph versions outside the registry', async () => {
  graphApi.computationOptions.mockResolvedValueOnce({data:{sources:[{ontology_id:'ceim-motor-new',publication_id:'motor-run',name:'Induction motor mBOM'}]}});
  const view=render(<ReportsTab searchResults={[]} graphData={{nodes:[],links:[]}}/>);
  expect(await screen.findByRole('option',{name:'Induction motor mBOM'})).toHaveValue('ceim-motor-new');
  const select=screen.getByLabelText('Report ontology');
  const {fireEvent}=await import('@testing-library/react');
  fireEvent.change(select,{target:{value:'ceim-motor-new'}});
  await waitFor(()=>expect(graphApi.getMetrics).toHaveBeenCalledWith('ceim-motor-new',expect.any(AbortSignal),''));
  view.unmount();window.history.replaceState(null,'','#/reports');
});

test('report rows use declared RDF types without changing identity or inventing a business label',()=>{
 const row=normalizeReportNode({elementId:'graph-1',labels:['resource'],properties:{label:'000886 Rotor Shaft',rdf_types:['http://www.w3.org/2002/07/owl#NamedIndividual','https://example.org/Part']}});
 expect(row.type).toBe('Part');expect(row.name).toBe('000886 Rotor Shaft');expect(row.elementId).toBe('graph-1');
 expect(normalizeReportNode({elementId:'anonymous',labels:['resource'],properties:{}}).type).toBe('resource');
 expect(normalizeReportNode({elementId:'property',labels:['ObjectProperty'],properties:{rdf_types:['https://example.org/Part']}}).type).toBe('ObjectProperty');
});
test('CSV exports preserve nested evidence and numeric values while preventing executable text',()=>{
 expect(escapeCsv('=HYPERLINK("https://example.org")')).toMatch(/^"'/);
 expect(escapeCsv('  @SUM(A1)')).toMatch(/^"'/);
 expect(escapeCsv(-2)).toBe('"-2"');expect(escapeCsv('-2.5')).toBe('"-2.5"');
 expect(escapeCsv(['Part','Assembly'])).toContain('[""Part"",""Assembly""]');
});
