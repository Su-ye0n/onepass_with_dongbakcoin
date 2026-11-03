BEGIN;

DO $$
BEGIN
    UPDATE user_profile
    SET department = '미술과',
        updated_at = CURRENT_TIMESTAMP
    WHERE user_id = 'USER_001';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Demo profile USER_001 must exist before updating student info';
    END IF;

    UPDATE user_identity_card
    SET subtitle = '미술과 · 24학번 · 휴학 (데모)'
    WHERE identity_card_id = 'DEMO_STUDENT_USER_001'
      AND user_id = 'USER_001'
      AND card_type = 'STUDENT';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Demo student identity card for USER_001 must exist before updating student info';
    END IF;
END $$;

COMMIT;
