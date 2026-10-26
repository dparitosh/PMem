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
  const status=String(run.status || 'unknown');
  const failed=['failed','validation_failed','cancelled'].includes(status);
  const complete=['completed','quality_warning'].includes(status);
  const publication=run.output_manifest?.publication;
  const published=publication?.status==='published' && !!publication.publication_id;
  const reason=run.failure?.message || run.last_error || (status==='validation_failed' ? 'Semantic validation did not conform. Review the retained report.' : '');
  const counts=run.output_manifest?.counts || {};
  const entities=counts.normalized_entities ?? counts.accepted_records;
  const relationships=counts.normalized_relationships;
  const message=failed ? `Run ${run.run_id}: ${reason || status}` : published ? `knowledge graph publication receipt retained for run ${run.run_id}.` : complete ? `Validation completed for run ${run.run_id}. Graph publication is pending; review and publish in Data Flow.` : `Governed run ${run.run_id}: ${status}. Open Data Flow for retained evidence.`;
  return {dataJobRunId:run.run_id,governedImport:true,stage:failed?'error':complete?'complete':'convert',backendStage:status,status,
    progress:complete?100:10,error:failed,committed:published,qualityWarning:status==='quality_warning',message,
    entities:entities ?? 0,relationships:relationships ?? 0,
    stats:{...(entities !== undefined ? {entities_found:entities} : {}),...(relationships !== undefined ? {relationships_found:relationships} : {})},
    lastUpdatedAt:new Date().toISOString()};
}
