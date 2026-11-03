BEGIN;

CREATE TABLE IF NOT EXISTS user_profile (
    user_id TEXT PRIMARY KEY
        REFERENCES "user"(user_id) ON DELETE CASCADE,
    display_name TEXT,
    student_card_id TEXT,
    phone_number TEXT,
    address TEXT,
    source_mode TEXT NOT NULL DEFAULT 'SYNTHETIC',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_topup_request_id
    ON ledger (request_id)
    WHERE event_type = 'TOPUP' AND request_id IS NOT NULL;

COMMIT;
