BEGIN;

CREATE TABLE IF NOT EXISTS user_credential (
    username TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE
        REFERENCES "user"(user_id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_session (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL
        REFERENCES "user"(user_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_user_session_user_id
    ON user_session (user_id);
CREATE INDEX IF NOT EXISTS ix_user_session_expires_at
    ON user_session (expires_at);

COMMIT;
