export function requireRunManifest(value) {
  const run = value?.run_manifest || value?.run;
  if (typeof run?.run_id !== 'string' || !run.run_id.trim()) throw new Error('The service did not return a durable run ID. Reconcile server state before retrying.');
  return run;
}
export function pipelineRunLink(runId) { return `#/data-flow/${encodeURIComponent(runId)}`; }
export function readRequestedRunId(hash = '') {
  const segment = String(hash).split('?')[0].split('/')[2];
  try { return segment ? decodeURIComponent(segment) : ''; } catch { return ''; }
}
export function governedRunStatus(run) {
  const status = String(run.status || 'unknown');
  return { dataJobRunId: run.run_id, governedImport: true, stage: ['completed', 'quality_warning', 'failed', 'cancelled'].includes(status) ? 'complete' : 'convert', backendStage: status, status,
    progress: ['completed', 'quality_warning'].includes(status) ? 100 : 10, error: status === 'failed' || status === 'cancelled',
    qualityWarning: status === 'quality_warning', message: status === 'quality_warning' ? `Run ${run.run_id} finished with quality findings. Review retained evidence in Data Flow before publication.` : `Governed run ${run.run_id}: ${status}. Open Data Flow for retained evidence.`, lastUpdatedAt: new Date().toISOString() };
}
