-- Support bounded newest captured-event pages as retained event history grows.
CREATE INDEX IF NOT EXISTS idx_depo_registry_capture_recent
ON depo_registry(namespace, (COALESCE(value->>'captured_at','')) DESC, key DESC)
WHERE namespace = 'speed_path_events';
