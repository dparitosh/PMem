-- Support bounded active ontology pages without sorting the entire registry.
-- Applied transactionally during the stopped-service upgrade maintenance window.
CREATE INDEX idx_depo_ontology_catalog_created
ON depo_registry (namespace, (COALESCE(value->>'created_at', '')) DESC, key DESC)
WHERE COALESCE(value->>'status', '') <> 'superseded';
