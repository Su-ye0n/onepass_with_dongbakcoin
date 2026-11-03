BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM "user"
        WHERE user_id = 'USER_001'
          AND (
              user_type IS DISTINCT FROM 'SYNTHETIC'
              OR origin_type IS DISTINCT FROM 'SYNTHETIC'
          )
    ) THEN
        RAISE EXCEPTION 'Demo user USER_001 conflicts with a non-synthetic user';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM db_wallet
        WHERE wallet_id = 'WALLET_USER_001'
          AND user_id <> 'USER_001'
    ) THEN
        RAISE EXCEPTION 'Demo wallet WALLET_USER_001 belongs to another user';
    END IF;
END $$;

INSERT INTO "user" (user_id, user_type, origin_type, user_status)
VALUES ('USER_001', 'SYNTHETIC', 'SYNTHETIC', 'ACTIVE')
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO db_wallet (
    wallet_id,
    user_id,
    charge_won,
    cashback_won,
    policy_support_won,
    wallet_status,
    origin_type
)
VALUES (
    'WALLET_USER_001',
    'USER_001',
    30000,
    0,
    0,
    'ACTIVE',
    'SYNTHETIC'
)
ON CONFLICT (wallet_id) DO NOTHING;

INSERT INTO user_profile (
    user_id,
    display_name,
    student_card_id,
    university,
    department,
    phone_number,
    address,
    source_mode
)
VALUES (
    'USER_001',
    '김개미',
    's_123',
    '갈매기 대학교',
    '철학과',
    '010-0000-0000',
    '부산광역시 (데모 주소)',
    'SYNTHETIC'
)
ON CONFLICT (user_id) DO NOTHING;

COMMIT;
