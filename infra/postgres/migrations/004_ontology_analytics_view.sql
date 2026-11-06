CREATE VIEW depo_ontology_analytics AS
SELECT key AS ontology_id,
       value->>'ontology_name' AS ontology_name,
       value->>'lifecycle_status' AS lifecycle_status,
       value->>'semantic_completeness' AS semantic_completeness,
       value->>'schema_set_digest' AS schema_set_digest,
       value->>'analytics_profile_artifact_id' AS analytics_profile_artifact_id,
       CASE WHEN jsonb_typeof(value->'statistics'->'triples') = 'number' THEN (value->'statistics'->>'triples')::numeric END AS triples,
       CASE WHEN jsonb_typeof(value->'statistics'->'classes') = 'number' THEN (value->'statistics'->>'classes')::numeric END AS classes,
       CASE WHEN jsonb_typeof(value->'statistics'->'object_properties') = 'number' THEN (value->'statistics'->>'object_properties')::numeric END AS object_properties,
       CASE WHEN jsonb_typeof(value->'statistics'->'datatype_properties') = 'number' THEN (value->'statistics'->>'datatype_properties')::numeric END AS datatype_properties
FROM depo_registry WHERE namespace = 'ontology_catalog';
