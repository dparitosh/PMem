import { render, screen } from '@testing-library/react';
import { ResultProvenance } from './ResultProvenance';

test('graph result states its source, policy status and that approval is not granted', () => {
  render(<ResultProvenance mode="graph" policy={{ status: 'passed' }} />);
  expect(screen.getByText('Direct graph read')).toBeVisible();
  expect(screen.getByText('Policy checks passed')).toBeVisible();
  expect(screen.getByText('Not granted. Evidence for review only.')).toBeVisible();
});

test('agent result cites its observation and reports unknown policy honestly', () => {
  render(<ResultProvenance mode="agent" policy={undefined} observationId="observation-2" />);
  expect(screen.getByText(/cites observation observation-2/)).toBeVisible();
  expect(screen.getByText('Policy status not reported')).toBeVisible();
});
