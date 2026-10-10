import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
const mocks = vi.hoisted(() => ({ getMetrics: vi.fn(), fetchOntologies: vi.fn() }));
vi.mock('@siemens/ix-react', () => {
  const Container = ({ children }) => <div>{children}</div>;
  return { IxBadge: Container, IxButton: Container, IxCard: Container, IxCardContent: Container, IxCardTitle: Container, IxCol: Container, IxLayoutGrid: Container };
});
vi.mock('../services/graphApi', () => ({ graphApi: { getMetrics: mocks.getMetrics } }));
vi.mock('../contexts/OntologyContext', () => ({ useOntologies: () => ({ ontologies: [{ ontology_id: 'qif-id', ontology_prefix: 'qif', name: 'QIF' }], fetchOntologies: mocks.fetchOntologies }) }));
vi.mock('./Chatbot', () => ({ default: () => <div>Chat ready</div> }));
import LandingPage from './LandingPage';

test('scope selection refreshes metrics using identity and namespace prefix', async () => {
  mocks.getMetrics.mockImplementation(async (id) => ({ data: { resources: 20, classes: id ? 7 : 12, scope: { sampled: false, type: 'published_rdf_projection', ontology_id: id } } }));
  render(<LandingPage />);
  await screen.findByText('12');
  fireEvent.change(screen.getByRole('combobox', { name: 'Ontology scope' }), { target: { value: 'qif-id' } });
  await screen.findByText('7');
  await waitFor(() => expect(mocks.getMetrics).toHaveBeenLastCalledWith('qif-id', expect.any(AbortSignal), 'qif'));
  expect(screen.getByRole('region', { name: 'Graph profile metrics' })).toHaveAttribute('tabindex', '0');
  expect(screen.getByText('Chat ready')).toBeVisible();
});
