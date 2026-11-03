BEGIN;

CREATE TABLE IF NOT EXISTS user_identity_card (
    identity_card_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL
        REFERENCES "user"(user_id) ON DELETE CASCADE,
    card_type TEXT NOT NULL,
    issuer_name TEXT NOT NULL,
    title TEXT NOT NULL,
    holder_name TEXT NOT NULL,
    subtitle TEXT NOT NULL,
    status TEXT NOT NULL,
    service_summary TEXT NOT NULL,
    credential_label TEXT NOT NULL,
    source_mode TEXT NOT NULL DEFAULT 'SYNTHETIC',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_user_identity_card_user_id
    ON user_identity_card (user_id);

COMMIT;
