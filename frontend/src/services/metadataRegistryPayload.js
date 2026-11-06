export function metadataAssetsPayload(body) {
  if (!body || !Array.isArray(body.assets) || body.assets.some(asset => !asset || typeof asset !== 'object'
    || typeof asset.asset_id !== 'string' || !asset.asset_id.trim()
    || typeof asset.name !== 'string' || typeof asset.lifecycle_status !== 'string'
    || ['definition', 'asset_type', 'domain', 'owner', 'steward', 'version'].some(field =>
      asset[field] != null && typeof asset[field] !== 'string'))) {
    throw new Error('Metadata registry returned an invalid asset list. Refresh or check the ontology service.');
  }
  return body.assets;
}

export function dictionaryAssetDraft(node, ontology) {
  if (!ontology?.ontology_id || !node?.term_id || !node.source) throw new Error('Select a term with a registered ontology identity.');
  const assetId = `ontology-term:${[ontology.ontology_id, node.source, node.term_id].map(encodeURIComponent).join(':')}`;
  if (assetId.length > 200) throw new Error('Term identity is too long for automatic registration. Register this term manually with its source reference.');
  return { asset_id: assetId, persistent_id: assetId, name: node.label || node.term_id,
    definition: node.definition || '', asset_type: node.source === 'class' ? 'EntityType' : 'DataElement',
    owner: ontology.owner || '', steward: ontology.steward || '', domain: ontology.domain || '',
    source_system: 'ontology', namespace_prefix: ontology.prefix || '', namespace_uri: ontology.namespace || '',
    ontology_uri: ontology.namespace || '', implementation_ref: node.term_id,
    lifecycle_status: 'draft', version: '1.0.0' };
}
