-- Immutable RDF snapshots shared by reporting and analysis workers.
CREATE TABLE depo_semantic_datasets (
 dataset_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, artifact_id TEXT NOT NULL,
 projection_version TEXT NOT NULL, metadata JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE depo_semantic_terms (
 dataset_id TEXT NOT NULL REFERENCES depo_semantic_datasets(dataset_id) ON DELETE CASCADE,
 iri TEXT NOT NULL, namespace_uri TEXT NOT NULL, label TEXT NOT NULL,
 description TEXT NOT NULL, term_kind TEXT NOT NULL,
 types TEXT[] NOT NULL, PRIMARY KEY(dataset_id,iri)
);
CREATE TABLE depo_semantic_namespaces (
 dataset_id TEXT NOT NULL REFERENCES depo_semantic_datasets(dataset_id) ON DELETE CASCADE,
 namespace_uri TEXT NOT NULL, prefix TEXT NOT NULL,
 PRIMARY KEY(dataset_id,namespace_uri,prefix)
);
CREATE TABLE depo_semantic_values (
 dataset_id TEXT NOT NULL REFERENCES depo_semantic_datasets(dataset_id) ON DELETE CASCADE,
 fact_id TEXT NOT NULL, subject_iri TEXT NOT NULL, property_iri TEXT NOT NULL,
 value_kind TEXT NOT NULL CHECK(value_kind IN ('literal','iri','blank')),
 lexical_value TEXT NOT NULL, datatype_iri TEXT NOT NULL, language TEXT NOT NULL,
 numeric_value NUMERIC, PRIMARY KEY(dataset_id,fact_id),
 FOREIGN KEY(dataset_id,subject_iri) REFERENCES depo_semantic_terms(dataset_id,iri)
);
CREATE INDEX idx_semantic_terms_scope ON depo_semantic_terms(dataset_id,namespace_uri,term_kind,iri);
CREATE INDEX idx_semantic_terms_types ON depo_semantic_terms USING gin(types);
CREATE INDEX idx_semantic_values_entity ON depo_semantic_values(dataset_id,subject_iri,property_iri);
CREATE INDEX idx_semantic_values_property ON depo_semantic_values(dataset_id,property_iri,subject_iri);
CREATE INDEX idx_semantic_values_numeric ON depo_semantic_values(dataset_id,property_iri,numeric_value)
 WHERE numeric_value IS NOT NULL;
CREATE INDEX idx_semantic_datasets_source ON depo_semantic_datasets(source_id,created_at DESC,dataset_id);
