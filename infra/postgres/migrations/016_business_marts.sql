-- Governed model versions and atomic, immutable analytics marts.
CREATE TABLE depo_analytics_models (
 model_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES depo_semantic_datasets(dataset_id),
 name TEXT NOT NULL, version TEXT NOT NULL, definition JSONB NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('draft','approved')), created_by TEXT NOT NULL,
 approved_by TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), approved_at TIMESTAMPTZ,
 UNIQUE(dataset_id,name,version),
 CHECK ((status='approved')=(approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE INDEX idx_analytics_models_dataset ON depo_analytics_models(dataset_id,status,created_at DESC);
CREATE TABLE depo_analytics_marts (
 mart_id TEXT PRIMARY KEY, model_id TEXT NOT NULL UNIQUE REFERENCES depo_analytics_models(model_id),
 dataset_id TEXT NOT NULL REFERENCES depo_semantic_datasets(dataset_id), receipt JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE depo_analytics_dim_entity (
 mart_id TEXT NOT NULL REFERENCES depo_analytics_marts(mart_id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('product','part','requirement','process')),
 entity_iri TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL,
 namespace_uri TEXT NOT NULL, PRIMARY KEY(mart_id,role,entity_iri)
);
CREATE TABLE depo_analytics_ods_value (
 mart_id TEXT NOT NULL REFERENCES depo_analytics_marts(mart_id) ON DELETE CASCADE,
 fact_id TEXT NOT NULL, entity_iri TEXT NOT NULL, property_iri TEXT NOT NULL,
 value_kind TEXT NOT NULL, value TEXT NOT NULL, datatype TEXT NOT NULL,
 language TEXT NOT NULL, numeric_value NUMERIC, PRIMARY KEY(mart_id,fact_id)
);
CREATE INDEX idx_analytics_ods_entity ON depo_analytics_ods_value(mart_id,entity_iri,property_iri);
CREATE TABLE depo_analytics_fact_link (
 mart_id TEXT NOT NULL REFERENCES depo_analytics_marts(mart_id) ON DELETE CASCADE,
 source_role TEXT NOT NULL, source_iri TEXT NOT NULL, relation TEXT NOT NULL,
 target_role TEXT NOT NULL, target_iri TEXT NOT NULL,
 PRIMARY KEY(mart_id,source_role,source_iri,relation,target_role,target_iri),
 FOREIGN KEY(mart_id,source_role,source_iri) REFERENCES depo_analytics_dim_entity(mart_id,role,entity_iri),
 FOREIGN KEY(mart_id,target_role,target_iri) REFERENCES depo_analytics_dim_entity(mart_id,role,entity_iri)
);
CREATE INDEX idx_analytics_links_target ON depo_analytics_fact_link(mart_id,target_role,target_iri);
CREATE TABLE depo_analytics_fact_measure (
 mart_id TEXT NOT NULL, role TEXT NOT NULL, entity_iri TEXT NOT NULL,
 measure TEXT NOT NULL, value NUMERIC NOT NULL, unit TEXT NOT NULL,
 PRIMARY KEY(mart_id,role,entity_iri,measure),
 FOREIGN KEY(mart_id,role,entity_iri) REFERENCES depo_analytics_dim_entity(mart_id,role,entity_iri)
);
CREATE TABLE depo_analytics_fact_kpi (
 mart_id TEXT NOT NULL REFERENCES depo_analytics_marts(mart_id) ON DELETE CASCADE,
 measure TEXT NOT NULL, value NUMERIC, unit TEXT NOT NULL, formula TEXT NOT NULL,
 population BIGINT NOT NULL, status TEXT NOT NULL, PRIMARY KEY(mart_id,measure)
);
CREATE VIEW depo_analytics_dim_product AS SELECT * FROM depo_analytics_dim_entity WHERE role='product';
CREATE VIEW depo_analytics_dim_part AS SELECT * FROM depo_analytics_dim_entity WHERE role='part';
CREATE VIEW depo_analytics_dim_requirement AS SELECT * FROM depo_analytics_dim_entity WHERE role='requirement';
CREATE VIEW depo_analytics_dim_process AS SELECT * FROM depo_analytics_dim_entity WHERE role='process';
