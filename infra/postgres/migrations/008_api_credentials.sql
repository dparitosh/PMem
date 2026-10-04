CREATE TABLE depo_api_credentials (
    profile TEXT PRIMARY KEY,
    salt TEXT NOT NULL,
    digest TEXT NOT NULL,
    actor TEXT NOT NULL CHECK (length(actor) > 0),
    expires_at TIMESTAMPTZ,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(salt) = 64 AND length(digest) = 64)
);
CREATE TABLE depo_api_credential_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('bootstrap', 'rotate', 'revoke')),
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
