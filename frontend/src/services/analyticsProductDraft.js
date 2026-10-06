export function publicationFromDraft(draft, fields, idempotencyKey) {
  if (!draft || draft.product_kind !== 'schema-design-evidence') throw new Error('Select a schema design draft.');
  const required = ['product_id', 'name', 'version', 'owner', 'steward', 'classification', 'approved_by', 'asset_id', 'release_version'];
  for (const field of required) if (!String(fields[field] || '').trim()) throw new Error(`${field} is required.`);
  if (!/^[A-Za-z][A-Za-z0-9._-]{0,127}$/.test(fields.product_id)) throw new Error('Product ID must start with a letter and contain only letters, numbers, dots, underscores or hyphens.');
  const artifacts = (draft.artifacts || []).map(item => typeof item === 'string' ? { artifact_id: item } : { artifact_id: item?.artifact_id });
  if (!artifacts.length || artifacts.some(item => !item.artifact_id)) throw new Error('Draft has no usable retained artifact references.');
  return { product_id: fields.product_id.trim(), name: fields.name.trim(), version: fields.version.trim(),
    domain: draft.domain || 'semantic-engineering', owner: fields.owner.trim(), steward: fields.steward.trim(),
    classification: fields.classification.trim(), lifecycle_state: 'published', approved_by: fields.approved_by.trim(),
    product_kind: draft.product_kind, analytics_readiness: draft.analytics_readiness,
    quality_status: draft.quality_status || 'requires_review', artifacts,
    semantic_releases: [{ asset_id: fields.asset_id.trim(), version: fields.release_version.trim(), lifecycle_status: 'approved' }],
    idempotency_key: idempotencyKey };
}

// These responses reject the request before publication; transport/server errors
// retain the original identity because a write may have completed.
export function isDefinitivePublicationRejection(error) {
  return [400, 401, 403, 404, 405, 422].includes(error?.response?.status);
}
