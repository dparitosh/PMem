-- Name the credential checks so verification can establish their semantics.
-- Existing migration 008 remains immutable; these also repair missing checks.
ALTER TABLE depo_api_credentials
    ADD CONSTRAINT depo_api_credentials_actor_nonempty CHECK (length(actor) > 0),
    ADD CONSTRAINT depo_api_credentials_digest_lengths CHECK (length(salt) = 64 AND length(digest) = 64);
ALTER TABLE depo_api_credential_events
    ADD CONSTRAINT depo_api_credential_events_action_valid CHECK (action IN ('bootstrap', 'rotate', 'revoke'));
ALTER TABLE depo_api_credentials ALTER COLUMN revoked SET DEFAULT FALSE;
ALTER TABLE depo_api_credentials ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE depo_api_credential_events ALTER COLUMN created_at SET DEFAULT now();
