import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi, test, expect } from 'vitest';
import OntologyOslcReport from './OntologyOslcReport';
import graphApi from '../services/graphApi';

vi.mock('../services/graphApi', () => ({ default: { getOntologyReport: vi.fn() } }));
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
  expect(await screen.findByRole('alert')).toHaveTextContent('OSLC report unavailable');
  expect(screen.queryByText(/12 graph records/)).toBeNull();
});
