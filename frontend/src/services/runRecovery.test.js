import { reportRunRecovery } from './runRecovery';
import { vi } from 'vitest';

test.each([
  ['/api/v1/pipeline/jobs/definitions/load/1/run', 'pipeline', 'pipeline'],
  ['/api/v1/pipeline/jobs/runs/load/reconcile-analytics', undefined, 'pipeline'],
  ['/api/v1/runs', 'workflow', 'workflow'],
  ['/api/v1/integrations/dt-requirements-design/runs/id', undefined, 'dt'],
])('retains the execution family for %s', (url, retainedKind, expected) => {
  const receive = vi.fn();
  window.addEventListener('depo:run-recovery', receive);
  try {
    reportRunRecovery({ config: { url }, response: { headers: { 'x-depo-run-id': 'retained-run', 'x-depo-run-kind': retainedKind } } });
    expect(receive.mock.calls[0][0].detail).toEqual({ runId: 'retained-run', kind: expected });
  } finally { window.removeEventListener('depo:run-recovery', receive); }
});
