const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

export function qualityRunsPayload(value) {
  if (!Array.isArray(value) || value.some(run => !object(run) || typeof run.run_id !== 'string' || !run.run_id.trim()
    || ['job_type', 'job_id', 'quality_profile', 'status'].some(key => run[key] != null && typeof run[key] !== 'string')
    || (run.output_manifest != null && !object(run.output_manifest)))) {
    throw new Error('The pipeline returned an invalid run list.');
  }
  return value;
}

export function requirementsPayload(value) {
  if (!Array.isArray(value) || value.some(row => !object(row)
    || (row.context_links != null && (!Array.isArray(row.context_links) || row.context_links.some(link => !object(link))))
    || ['requirement_id', 'id', 'element_id', 'title', 'text', 'semantic_role', 'ontology_class', 'source', 'source_file', 'status']
      .some(key => row[key] != null && typeof row[key] !== 'string')
    || (row.labels != null && (!Array.isArray(row.labels) || row.labels.some(label => typeof label !== 'string'))))) {
    throw new Error('The requirements service returned an invalid requirement list.');
  }
  return value;
}
