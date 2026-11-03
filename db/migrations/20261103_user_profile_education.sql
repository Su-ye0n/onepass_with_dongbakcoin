BEGIN;

ALTER TABLE user_profile
    ADD COLUMN IF NOT EXISTS university TEXT;
ALTER TABLE user_profile
    ADD COLUMN IF NOT EXISTS department TEXT;

COMMIT;
