CREATE TABLE IF NOT EXISTS depo_metadata_assets (
    asset_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK (revision > 0),
    value JSONB NOT NULL CHECK (jsonb_typeof(value) = 'object'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS depo_metadata_events (
    event_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES depo_metadata_assets(asset_id),
    revision INTEGER NOT NULL,
    value JSONB NOT NULL CHECK (jsonb_typeof(value) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(asset_id, revision)
);

CREATE TABLE IF NOT EXISTS depo_metadata_outbox (
    event_id TEXT PRIMARY KEY REFERENCES depo_metadata_events(event_id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','published')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metadata_pending ON depo_metadata_outbox(created_at) WHERE status = 'pending';
