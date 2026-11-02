
PRAGMA foreign_keys = ON;

-- P0 schema based on the confirmed 20-table ERD.
-- Monetary amounts: integer KRW.
-- Rates: decimal strings converted with Decimal in Python.
-- All intervals: [valid_from, valid_to).
-- Source values: VERIFIED / SYNTHETIC / ASSUMED / PENDING.

CREATE TABLE CARD_PRODUCT (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    issuer TEXT NOT NULL,
    card_type TEXT NOT NULL CHECK (
        card_type IN (
            'DONGBAEK_CHECK', 'DONGBAEK_PREPAID',
            'BANK_CHECK', 'BANK_CREDIT'
        )
    ),
    product_status TEXT NOT NULL DEFAULT 'TEST_ONLY',
    terms_version TEXT,
    source_status TEXT NOT NULL DEFAULT 'SYNTHETIC',
    source_ref TEXT
);

CREATE TABLE BENEFIT_RULE (
    rule_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES CARD_PRODUCT(product_id),
    benefit_name TEXT NOT NULL,
    benefit_type TEXT NOT NULL CHECK (
        benefit_type IN ('RATE', 'FIXED')
    ),
    rate TEXT,
    fixed_amount_won INTEGER,
    min_amount_won INTEGER NOT NULL DEFAULT 0,
    per_tx_cap_won INTEGER,
    monthly_cap_won INTEGER,
    shared_cap_group TEXT,
    day_condition TEXT NOT NULL DEFAULT 'ALL',
    monthly_count_cap INTEGER,
    perf_threshold_won INTEGER NOT NULL DEFAULT 0,
    perf_basis_code TEXT,
    reward_unit TEXT NOT NULL DEFAULT 'CASH',
    stack_rule TEXT NOT NULL DEFAULT 'MAX_ONLY',
    payment_channel_required TEXT NOT NULL DEFAULT 'ANY',
    rounding_mode TEXT NOT NULL DEFAULT 'FLOOR',
    valid_from TEXT,
    valid_to TEXT,
    source_status TEXT NOT NULL DEFAULT 'SYNTHETIC',
    CHECK (valid_to IS NULL OR valid_from IS NULL
           OR valid_from < valid_to),
    CHECK (rate IS NULL OR CAST(rate AS REAL) >= 0),
    CHECK (min_amount_won >= 0),
    CHECK (monthly_count_cap IS NULL OR monthly_count_cap > 0)
);

CREATE TABLE BENEFIT_INDUSTRY (
    rule_id TEXT NOT NULL REFERENCES BENEFIT_RULE(rule_id),
    target_type TEXT NOT NULL CHECK (
        target_type IN ('CATEGORY', 'MERCHANT', 'CHANNEL')
    ),
    target_code TEXT NOT NULL,
    apply_type TEXT NOT NULL CHECK (
        apply_type IN ('INCLUDE', 'EXCLUDE')
    ),
    PRIMARY KEY (rule_id, target_type, target_code)
);

CREATE TABLE CARD_PERF_EXCLUDE (
    exclude_id INTEGER PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES CARD_PRODUCT(product_id),
    rule_id TEXT REFERENCES BENEFIT_RULE(rule_id),
    exclude_type TEXT NOT NULL,
    exclude_value TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    CHECK (valid_to IS NULL OR valid_from IS NULL
           OR valid_from < valid_to)
);

CREATE TABLE BENEFIT_CAP_TIER (
    tier_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES CARD_PRODUCT(product_id),
    cap_group TEXT NOT NULL,
    perf_min_won INTEGER NOT NULL CHECK (perf_min_won >= 0),
    monthly_cap_won INTEGER NOT NULL CHECK (monthly_cap_won >= 0),
    valid_from TEXT,
    valid_to TEXT,
    CHECK (valid_to IS NULL OR valid_from IS NULL
           OR valid_from < valid_to)
);

CREATE TABLE DB_POLICY (
    policy_id TEXT PRIMARY KEY,
    policy_name TEXT NOT NULL,
    policy_mode TEXT NOT NULL CHECK (
        policy_mode IN ('HISTORICAL', 'FROZEN_SCENARIO')
    ),
    monthly_cashback_base_cap_won INTEGER NOT NULL DEFAULT 0,
    monthly_charge_cap_won INTEGER,
    holding_balance_cap_won INTEGER,
    funding_order TEXT,
    rounding_mode TEXT NOT NULL DEFAULT 'FLOOR',
    valid_from TEXT,
    valid_to TEXT,
    source_status TEXT NOT NULL DEFAULT 'SYNTHETIC',
    policy_note TEXT,
    CHECK (valid_to IS NULL OR valid_from IS NULL
           OR valid_from < valid_to)
);

CREATE TABLE DB_POLICY_RATE (
    policy_id TEXT NOT NULL REFERENCES DB_POLICY(policy_id),
    sales_band TEXT NOT NULL CHECK (
        sales_band IN ('LE_10B', 'GT_10B_LE_30B', 'GT_30B')
    ),
    cashback_rate TEXT NOT NULL,
    eligible_funding_bucket TEXT,
    PRIMARY KEY (policy_id, sales_band)
);

CREATE TABLE DB_POLICY_BONUS (
    bonus_id INTEGER PRIMARY KEY,
    policy_id TEXT NOT NULL REFERENCES DB_POLICY(policy_id),
    bonus_name TEXT NOT NULL,
    bonus_type TEXT NOT NULL,
    sales_band TEXT,
    rate_mode TEXT,
    bonus_rate TEXT,
    fixed_won INTEGER,
    max_benefit_won INTEGER,
    payment_channel_required TEXT DEFAULT 'ANY',
    required_merchant_flag TEXT DEFAULT 'NONE',
    coupon_required INTEGER DEFAULT 0,
    min_payment_won INTEGER DEFAULT 0,
    excluded_category_codes TEXT,
    funding_bucket_scope TEXT,
    stack_rule TEXT DEFAULT 'PENDING',
    valid_from TEXT,
    valid_to TEXT,
    source_status TEXT NOT NULL DEFAULT 'SYNTHETIC',
    CHECK (valid_to IS NULL OR valid_from IS NULL
           OR valid_from < valid_to)
);

CREATE TABLE MERCHANT (
    merchant_id TEXT PRIMARY KEY,
    merchant_name TEXT,
    source_merchant_id TEXT,
    industry_code TEXT NOT NULL,
    dongbaek_status TEXT NOT NULL CHECK (
        dongbaek_status IN (
            'REGISTERED', 'NOT_REGISTERED', 'UNKNOWN'
        )
    ),
    sales_band TEXT NOT NULL CHECK (
        sales_band IN (
            'LE_10B', 'GT_10B_LE_30B', 'GT_30B', 'UNKNOWN'
        )
    ),
    sales_band_basis_at TEXT,
    is_good_price_shop INTEGER NOT NULL DEFAULT 0,
    is_dbplus_shop INTEGER NOT NULL DEFAULT 0,
    is_qr_merchant INTEGER NOT NULL DEFAULT 0,
    dbplus_discount_rate TEXT,
    region_code TEXT,
    source_status TEXT NOT NULL DEFAULT 'SYNTHETIC'
);

CREATE TABLE BENEFIT_CATEGORY_MAP (
    map_id INTEGER PRIMARY KEY,
    industry_code TEXT NOT NULL,
    std_category TEXT NOT NULL,
    screen_group_code TEXT NOT NULL,
    mapping_confidence TEXT NOT NULL DEFAULT 'ASSUMED',
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    mapping_note TEXT,
    UNIQUE (industry_code, valid_from),
    CHECK (valid_to IS NULL OR valid_from < valid_to)
);

CREATE TABLE "USER" (
    user_id TEXT PRIMARY KEY,
    user_type TEXT NOT NULL DEFAULT 'SYNTHETIC',
    origin_type TEXT NOT NULL DEFAULT 'SYNTHETIC',
    user_status TEXT NOT NULL DEFAULT 'ACTIVE',
    age_band TEXT,
    district_code TEXT,
    spend_band TEXT,
    card_ownership_combo TEXT,
    estimated_monthly_spend_won INTEGER,
    dongbaek_usage_level TEXT,
    seed_id TEXT,
    created_at TEXT
);

CREATE TABLE ONECARD (
    onecard_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES "USER"(user_id),
    default_mode TEXT NOT NULL DEFAULT 'ONECARD'
        CHECK (default_mode IN ('ONECARD', 'DIRECT')),
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    issued_at TEXT,
    expires_at TEXT,
    replaces_onecard_id TEXT REFERENCES ONECARD(onecard_id),
    active_from TEXT,
    active_to TEXT,
    created_at TEXT,
    CHECK (active_to IS NULL OR active_from IS NULL
           OR active_from < active_to)
);

CREATE TABLE USER_CATEGORY (
    user_id TEXT NOT NULL REFERENCES "USER"(user_id),
    user_category_code TEXT NOT NULL,
    label TEXT,
    display_order INTEGER,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, user_category_code)
);

CREATE TABLE ACCOUNT (
    account_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES "USER"(user_id),
    account_role TEXT NOT NULL,
    account_status TEXT NOT NULL DEFAULT 'ACTIVE',
    opening_balance_won INTEGER NOT NULL DEFAULT 0
        CHECK (opening_balance_won >= 0),
    opening_balance_at TEXT,
    origin_type TEXT NOT NULL DEFAULT 'SYNTHETIC'
);

CREATE TABLE DB_WALLET (
    wallet_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES "USER"(user_id),
    charge_won INTEGER NOT NULL DEFAULT 0 CHECK (charge_won >= 0),
    cashback_won INTEGER NOT NULL DEFAULT 0 CHECK (cashback_won >= 0),
    policy_support_won INTEGER NOT NULL DEFAULT 0
        CHECK (policy_support_won >= 0),
    opening_balance_at TEXT,
    wallet_status TEXT NOT NULL DEFAULT 'ACTIVE',
    origin_type TEXT NOT NULL DEFAULT 'SYNTHETIC'
);

CREATE TABLE USER_CARD (
    user_card_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES "USER"(user_id),
    product_id TEXT NOT NULL REFERENCES CARD_PRODUCT(product_id),
    db_wallet_id TEXT REFERENCES DB_WALLET(wallet_id),
    linked_account_id TEXT REFERENCES ACCOUNT(account_id),
    card_status TEXT NOT NULL DEFAULT 'ACTIVE',
    credit_limit_won INTEGER DEFAULT 0
        CHECK (credit_limit_won >= 0),
    default_preference_rank INTEGER,
    expires_at TEXT,
    registered_ref TEXT,
    active_from TEXT,
    active_to TEXT,
    CHECK (active_to IS NULL OR active_from IS NULL
           OR active_from < active_to)
);

CREATE TABLE USER_CATEGORY_PRIORITY (
    priority_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES "USER"(user_id),
    user_category_code TEXT NOT NULL,
    user_card_id TEXT NOT NULL REFERENCES USER_CARD(user_card_id),
    priority_group INTEGER NOT NULL CHECK (priority_group >= 1),
    valid_from TEXT,
    valid_to TEXT,
    setting_version TEXT,
    FOREIGN KEY (user_id, user_category_code)
        REFERENCES USER_CATEGORY(user_id, user_category_code),
    CHECK (valid_to IS NULL OR valid_from IS NULL
           OR valid_from < valid_to)
);

CREATE TABLE LEDGER (
    ledger_id INTEGER PRIMARY KEY,
    tx_id TEXT,
    request_id TEXT,
    user_id TEXT NOT NULL REFERENCES "USER"(user_id),
    user_card_id TEXT REFERENCES USER_CARD(user_card_id),
    account_id TEXT REFERENCES ACCOUNT(account_id),
    wallet_id TEXT REFERENCES DB_WALLET(wallet_id),
    merchant_id TEXT REFERENCES MERCHANT(merchant_id),
    event_at TEXT NOT NULL,
    event_seq INTEGER NOT NULL DEFAULT 0,
    event_type TEXT NOT NULL,
    bucket_type TEXT NOT NULL,
    delta_won INTEGER NOT NULL DEFAULT 0,
    gross_purchase_won INTEGER DEFAULT 0,
    cashback_eligible_base_won INTEGER DEFAULT 0,
    awarded_benefit_won INTEGER DEFAULT 0,
    rule_id TEXT REFERENCES BENEFIT_RULE(rule_id),
    policy_id TEXT REFERENCES DB_POLICY(policy_id),
    reverses_ledger_id INTEGER REFERENCES LEDGER(ledger_id),
    approval_status TEXT,
    source_mode TEXT NOT NULL DEFAULT 'INITIAL',
    event_note TEXT
);

CREATE TABLE CARD_MONTH_CLOSE (
    user_card_id TEXT NOT NULL REFERENCES USER_CARD(user_card_id),
    base_month TEXT NOT NULL,
    spend_total_won INTEGER NOT NULL DEFAULT 0,
    benefit_total_won INTEGER NOT NULL DEFAULT 0,
    credit_used_won INTEGER NOT NULL DEFAULT 0,
    closed_at TEXT,
    source_mode TEXT NOT NULL DEFAULT 'ASSUMED',
    PRIMARY KEY (user_card_id, base_month)
);

CREATE TABLE CARD_PERF_MONTH_CLOSE (
    user_card_id TEXT NOT NULL REFERENCES USER_CARD(user_card_id),
    base_month TEXT NOT NULL,
    rule_id TEXT NOT NULL REFERENCES BENEFIT_RULE(rule_id),
    eligible_perf_won INTEGER NOT NULL DEFAULT 0,
    excluded_perf_won INTEGER NOT NULL DEFAULT 0,
    threshold_met INTEGER NOT NULL DEFAULT 0,
    rule_version TEXT,
    benefit_used_won INTEGER NOT NULL DEFAULT 0,
    closed_at TEXT,
    source_mode TEXT NOT NULL DEFAULT 'ASSUMED',
    PRIMARY KEY (user_card_id, base_month, rule_id)
);

CREATE INDEX idx_rule_product_date
    ON BENEFIT_RULE(product_id, valid_from, valid_to);

CREATE INDEX idx_merchant_industry
    ON MERCHANT(industry_code);

CREATE INDEX idx_ledger_user_date
    ON LEDGER(user_id, event_at, event_seq);

CREATE INDEX idx_card_user
    ON USER_CARD(user_id);
