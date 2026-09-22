CREATE TABLE IF NOT EXISTS depo_runtime_state (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY(kind, key)
);

CREATE TABLE IF NOT EXISTS depo_chat_messages (
    session_id TEXT NOT NULL,
    message_id BIGSERIAL PRIMARY KEY,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_depo_chat_messages ON depo_chat_messages(session_id, message_id);

CREATE TABLE IF NOT EXISTS depo_rate_limits (
    client_key TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_depo_rate_limits ON depo_rate_limits(client_key, created_at);
