// Apply to the configured semantic graph database during provisioning.
// Uniqueness is required for concurrency-safe publisher MERGE operations.
CREATE CONSTRAINT uq_ontologyresource_identity IF NOT EXISTS
FOR (n:OntologyResource) REQUIRE (n.ontology_id, n.iri) IS UNIQUE;
CREATE CONSTRAINT uq_ontologypublication_identity IF NOT EXISTS
FOR (n:OntologyPublication) REQUIRE (n.ontology_id, n.publication_id) IS UNIQUE;
CREATE CONSTRAINT depo_bridge_publication_id IF NOT EXISTS
FOR (p:DepoBridgePublication) REQUIRE p.publication_id IS UNIQUE;
// Unpublished batches remain outside all OntologyResource read projections.
CREATE CONSTRAINT uq_ontologystagedresource_identity IF NOT EXISTS
FOR (n:StagedOntologyResource) REQUIRE (n.ontology_id, n.publication_id, n.iri) IS UNIQUE;
// Retained nodes temporarily lose OntologyResource and its constraint index.
CREATE INDEX idx_depo_retained_ontology_identity IF NOT EXISTS
FOR (n:RetainedOntologyIdentity) ON (n.ontology_id, n.iri);
// Scope-only catalog/metrics reads cannot rely on an IRI value being supplied.
CREATE INDEX idx_depo_ontologyresource_scope IF NOT EXISTS
FOR (n:OntologyResource) ON (n.ontology_id);
// Legacy mapped resources may retain their owning scope as source_ontology.
CREATE INDEX idx_depo_ontologyresource_source_scope IF NOT EXISTS
FOR (n:OntologyResource) ON (n.source_ontology);
CALL db.awaitIndexes(60);
CREATE TEXT INDEX idx_depo_resource_search_label IF NOT EXISTS
FOR (n:OntologyResource) ON (n.search_label);
CREATE TEXT INDEX idx_depo_resource_search_iri IF NOT EXISTS
FOR (n:OntologyResource) ON (n.search_iri);
CREATE FULLTEXT INDEX idx_depo_context_evidence IF NOT EXISTS
FOR (n:GraphChunk|DatasheetChunk) ON EACH [n.content];
CALL db.awaitIndexes(60);
