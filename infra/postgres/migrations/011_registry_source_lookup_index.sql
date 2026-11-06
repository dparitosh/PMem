-- Source identities deduplicate engineering registration retries.
-- Include namespace and key to support the bounded ordered lookup.
CREATE INDEX idx_depo_registry_source_lookup
ON depo_registry (namespace, (value->>'source'), key);
