// Apply to the configured semantic graph database during provisioning.
// Non-destructive: accelerates publisher MERGE and relationship endpoint lookup.
CREATE INDEX idx_ontologyresource_identity IF NOT EXISTS
FOR (n:OntologyResource) ON (n.ontology_id, n.iri);
CALL db.awaitIndexes(60);
