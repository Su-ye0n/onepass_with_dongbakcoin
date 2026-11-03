BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM "user" WHERE user_id = 'USER_001'
    ) THEN
        RAISE EXCEPTION 'Demo user USER_001 must be seeded before kb_bridge';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM user_profile WHERE user_id = 'USER_001'
    ) THEN
        RAISE EXCEPTION 'Demo profile USER_001 must be seeded before kb_bridge';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM db_wallet
        WHERE user_id = 'USER_001' AND wallet_status = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION 'Demo wallet USER_001 must be seeded before kb_bridge';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM user_card
        WHERE user_id = 'USER_001'
          AND product_id = 'BNK_CR_P07'
          AND card_status = 'ACTIVE'
          AND credit_limit_won = 1500000
    ) THEN
        RAISE EXCEPTION 'Active Ding Ding demo card with expected limit is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM user_card
        WHERE user_id = 'USER_001'
          AND product_id = 'BNK_CK_P23'
          AND card_status = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION 'Active Green Check demo card is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM benefit_rule WHERE product_id = 'BNK_CR_P07'
    ) OR NOT EXISTS (
        SELECT 1 FROM benefit_rule WHERE product_id = 'BNK_CK_P23'
    ) THEN
        RAISE EXCEPTION 'Demo card benefit rules must be seeded before kb_bridge';
    END IF;
END $$;

UPDATE user_profile
SET display_name = '김개미',
    student_card_id = 's_123',
    university = '갈매기 대학교',
    department = '철학과',
    address = '부산광역시 영도구 (데모 주소)',
    updated_at = CURRENT_TIMESTAMP
WHERE user_id = 'USER_001';

INSERT INTO user_identity_card (
    identity_card_id,
    user_id,
    card_type,
    issuer_name,
    title,
    holder_name,
    subtitle,
    status,
    service_summary,
    credential_label,
    source_mode,
    created_at
)
VALUES
    (
        'c_001',
        'USER_001',
        'CIVIC',
        '부산광역시 영도구',
        '부산광역시 시민증',
        '김개미',
        '부산 영도구 · 데모 인증',
        'ACTIVE',
        '시민 인증 · 지역 혜택',
        '데모 시민증 · 실물 신분증 아님',
        'SYNTHETIC',
        CURRENT_TIMESTAMP
    ),
    (
        'DEMO_STUDENT_USER_001',
        'USER_001',
        'STUDENT',
        '갈매기 대학교',
        '갈매기 대학교 학생증',
        '김개미',
        '철학과 · 2024학번 · 휴학 (데모)',
        'ACTIVE',
        '도서관 출입 · 학식 할인 · 원카드 결제',
        '학생증 · 재학 인증',
        'SYNTHETIC',
        CURRENT_TIMESTAMP
    )
ON CONFLICT (identity_card_id) DO UPDATE
SET user_id = EXCLUDED.user_id,
    card_type = EXCLUDED.card_type,
    issuer_name = EXCLUDED.issuer_name,
    title = EXCLUDED.title,
    holder_name = EXCLUDED.holder_name,
    subtitle = EXCLUDED.subtitle,
    status = EXCLUDED.status,
    service_summary = EXCLUDED.service_summary,
    credential_label = EXCLUDED.credential_label,
    source_mode = EXCLUDED.source_mode;

INSERT INTO user_credential (username, user_id, password_hash, created_at)
VALUES (
    'kb_bridge',
    'USER_001',
    'pbkdf2_sha256$310000$lbe3ACu_z8Uo90xO02YypQ==$TiLE1SZstmunCoq0OY900o4Mdoz1wvnByc0zPYWb_MQ=',
    CURRENT_TIMESTAMP
)
ON CONFLICT (username) DO UPDATE
SET user_id = EXCLUDED.user_id,
    password_hash = EXCLUDED.password_hash;

COMMIT;
