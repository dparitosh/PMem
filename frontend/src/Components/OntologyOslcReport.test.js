import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi, test, expect } from 'vitest';
import OntologyOslcReport from './OntologyOslcReport';
import graphApi from '../services/graphApi';

vi.mock('../services/graphApi', () => ({ default: { getOntologyReport: vi.fn() } }));
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn(async()=>({data:{scope:'service_wide',ontology_scoped:false,capabilities:[
 {id:'trs',name:'Tracked Resource Set (TRS)',status:'available',counts:{'Tracked change position':23},workspace:'#/change-control',support:'Tracked change feed'},
 {id:'configuration',name:'Configuration Management',status:'available',counts:{'Release baselines':0},workspace:'#/change-control?source=releases',support:'Frozen baselines only'},
 {id:'automation',name:'Automation',status:'available',counts:{'Plan resources':2,'Request resources':4,'Result resources':4},workspace:'#/data-flow',support:'Retained automation adapter'},
]}}))}}));
vi.mock('./EChartPanel', () => ({ default: () => <div>Coverage chart</div> }));
const payload = id => ({ ontology_id: id, sampled: false, resources: 12, outgoing_links: 3,
  unmapped: 9, categories: [{ domain: 'RM', resource_type: 'requirements', count: 3 }], notes: [] });

test('late response from a previous ontology cannot replace the current scope', async () => {
  let oldResolve;
  graphApi.getOntologyReport.mockImplementationOnce(() => new Promise(resolve => { oldResolve = resolve; }))
    .mockResolvedValueOnce({ data: payload('reqif') });
  const view = render(<OntologyOslcReport ontologyId="qif" revision={0} />);
  view.rerender(<OntologyOslcReport ontologyId="reqif" revision={0} />);
  await screen.findByText(/12 graph records/);
  oldResolve({ data: { ...payload('qif'), resources: 99 } });
  await waitFor(() => expect(screen.queryByText(/99 graph records/)).toBeNull());
});

test('wrong-scope or malformed responses show an error rather than fabricated totals', async () => {
  graphApi.getOntologyReport.mockResolvedValueOnce({ data: payload('other') });
  render(<OntologyOslcReport ontologyId="qif" revision={0} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid ontology report response');
  expect(screen.queryByText(/12 graph records/)).toBeNull();
});


test('tracking configuration and automation remain separate from ontology classification', async () => {
 render(<OntologyOslcReport ontologyId="" revision={0}/>);
 const section=await screen.findByRole('region',{name:'OSLC lifecycle capabilities'});
 expect(await screen.findByText('Tracked change position: 23')).toBeVisible();
 expect(section).toHaveTextContent('Configuration Management');
 expect(section).toHaveTextContent('Automation');
 expect(section).toHaveTextContent('Release baselines: 0');
 expect(section).toHaveTextContent('Plan resources: 2');
 expect(section).toHaveTextContent('Platform-wide');
 expect(graphApi.getOntologyReport).not.toHaveBeenCalledWith('',expect.anything());
});
