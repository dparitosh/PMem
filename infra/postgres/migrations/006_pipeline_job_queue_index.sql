-- Bound worker claims to runnable data-job records instead of scanning the
-- complete JSON control-plane registry as retained run history grows.
CREATE INDEX IF NOT EXISTS idx_depo_pipeline_runnable
  ON depo_registry(updated_at, key)
  WHERE namespace = 'data_job_runs'
    AND value->>'status' IN ('queued', 'running');
