-- Existing invalid JSON is reported by VALIDATE; no customer rows are deleted.
ALTER TABLE depo_registry ADD CONSTRAINT depo_registry_value_object CHECK (jsonb_typeof(value) = 'object') NOT VALID;
ALTER TABLE depo_registry VALIDATE CONSTRAINT depo_registry_value_object;
ALTER TABLE depo_runtime_state ADD CONSTRAINT depo_runtime_state_value_object CHECK (jsonb_typeof(value) = 'object') NOT VALID;
ALTER TABLE depo_runtime_state VALIDATE CONSTRAINT depo_runtime_state_value_object;
CREATE INDEX idx_depo_registry_recent ON depo_registry(namespace, updated_at DESC, key);
