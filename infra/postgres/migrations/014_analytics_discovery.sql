-- Receipt-backed analytics inventory: versioned schema deduplication and newest run.
CREATE INDEX idx_depo_analytics_discovery
ON depo_registry ((value#>>'{output_manifest,ods_receipt,schema}'), updated_at DESC, key DESC)
WHERE namespace='data_job_runs'
  AND value->>'job_type'='xml-analytics-materialize'
  AND value->>'status'='completed'
  AND value#>>'{output_manifest,ods_receipt,status}'='completed';
