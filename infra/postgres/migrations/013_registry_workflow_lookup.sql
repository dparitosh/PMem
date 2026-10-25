-- Match bounded status pages and job-identity lookups as retained history grows.
CREATE INDEX idx_depo_registry_status_recent
ON depo_registry(namespace, (value->>'status'), updated_at DESC, key);

CREATE INDEX idx_depo_job_identity
ON depo_registry(namespace, (value->>'job_id'), (value->>'job_version'))
WHERE namespace = 'data_job_runs';
