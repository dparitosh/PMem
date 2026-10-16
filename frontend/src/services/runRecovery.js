import { config } from '../config';
const STORAGE_KEY = 'depo.runRecovery.v1';
const scope = () => JSON.stringify([config.gatewayUrl || '', config.semanticServiceUrls || {}]);
export function validRecoveryRun(run) {
  return run && ['workflow', 'pipeline', 'dt', 'tool'].includes(run.kind) && typeof run.runId === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(run.runId);
}
export function readRecoveryRuns() {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw || raw.length > 262144) return [];
    const saved = JSON.parse(raw);
    return saved.scope === scope() && Array.isArray(saved.runs) ? saved.runs.filter(validRecoveryRun) : [];
  } catch { return []; }
}
export function saveRecoveryRuns(runs) {
  try { window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ scope: scope(), runs: runs.filter(validRecoveryRun) })); } catch { /* Memory state remains available when storage is restricted. */ }
}
export function reportRunRecovery(error) {
  const id = error?.response?.headers?.get?.('X-DEPO-Run-ID') || error?.response?.headers?.['x-depo-run-id'];
  if (typeof id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(id)) return;
  const url = String(error?.config?.url || '');
  const retainedKind = error?.response?.headers?.get?.('X-DEPO-Run-Kind') || error?.response?.headers?.['x-depo-run-kind'];
  const kind = ['workflow', 'pipeline', 'dt', 'tool'].includes(retainedKind) ? retainedKind : url.includes('/api/v1/pipeline/') ? 'pipeline' : url.includes('/integrations/dt-requirements-design/runs') ? 'dt' : url.includes('/workflow-runs') ? 'workflow' : 'tool';
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('depo:run-recovery', { detail: { runId: id, kind } }));
}
