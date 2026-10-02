export function reportRunRecovery(error) {
  const id = error?.response?.headers?.get?.('X-DEPO-Run-ID') || error?.response?.headers?.['x-depo-run-id'];
  if (typeof id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(id)) return;
  const url = String(error?.config?.url || '');
  const kind = url.includes('/integrations/dt-requirements-design/runs') ? 'dt' : url.includes('/workflow-runs') ? 'workflow' : 'tool';
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('depo:run-recovery', { detail: { runId: id, kind } }));
}
