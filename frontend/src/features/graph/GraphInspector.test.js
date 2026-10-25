import React from 'react';
import { render, screen } from '@testing-library/react';
import GraphInspector from './GraphInspector';
import { ChangeImpactResult } from '../recommendations/ChangeImpactResult';

const insufficient = {
  change_entity: { name: 'Bearing noise' }, impact_score: null,
  evidence_status: 'insufficient',
  message: 'Impact is unknown; review the affected business records.',
};

test('graph inspector explains missing evidence without a zero or high impact score', () => {
  render(<GraphInspector recPanel={{open: true, service: 'change-impact', nodeName: 'Bearing noise', result: insufficient}}
    setRecPanel={vi.fn()} setActiveTab={vi.fn()} />);
  expect(screen.getByRole('status')).toHaveTextContent('Impact is unknown');
  expect(screen.queryByText(/\/100/)).not.toBeInTheDocument();
});

test('recommendations keeps unknown impact distinct from a safety conclusion', () => {
  render(<ChangeImpactResult data={insufficient} />);
  expect(screen.getByRole('status')).toHaveTextContent('Bearing noise');
  expect(screen.getByRole('status')).toHaveTextContent('Impact is unknown');
  expect(screen.queryByText(/Impact Score/)).not.toBeInTheDocument();
});
