PRAGMA foreign_keys = ON;
-- Minimal SQLite *simulation* schema. Not the entire PRD 40-table design.
CREATE TABLE IF NOT EXISTS sim_user (user_id TEXT PRIMARY KEY, db_charge INTEGER NOT NULL DEFAULT 0 CHECK(db_charge>=0), db_cashback INTEGER NOT NULL DEFAULT 0 CHECK(db_cashback>=0), db_grant INTEGER NOT NULL DEFAULT 0 CHECK(db_grant>=0), db_month_applied INTEGER NOT NULL DEFAULT 0 CHECK(db_month_applied>=0));
CREATE TABLE IF NOT EXISTS funding_account (account_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES sim_user(user_id), opening_balance_won INTEGER NOT NULL CHECK(opening_balance_won>=0));
CREATE TABLE IF NOT EXISTS card_product (product_id TEXT PRIMARY KEY, product_name TEXT NOT NULL, engine_type TEXT NOT NULL CHECK(engine_type IN ('CREDIT','DEBIT','DONGBAEK_CHECK')), source_status TEXT NOT NULL DEFAULT 'SIMULATED' CHECK(source_status IN ('SIMULATED','VERIFIED')));
CREATE TABLE IF NOT EXISTS user_card (user_card_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES sim_user(user_id), product_id TEXT NOT NULL REFERENCES card_product(product_id), account_id TEXT REFERENCES funding_account(account_id), credit_limit INTEGER NOT NULL DEFAULT 0 CHECK(credit_limit>=0), active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), lost INTEGER NOT NULL DEFAULT 0 CHECK(lost IN (0,1)), expired INTEGER NOT NULL DEFAULT 0 CHECK(expired IN (0,1)), prev_month_perf INTEGER NOT NULL DEFAULT 0 CHECK(prev_month_perf>=0));
CREATE TABLE IF NOT EXISTS merchant (merchant_id TEXT PRIMARY KEY,category_code TEXT NOT NULL,db_registration_status TEXT NOT NULL CHECK(db_registration_status IN ('REGISTERED','NOT_REGISTERED','UNKNOWN')),annual_sales_band TEXT NOT NULL CHECK(annual_sales_band IN ('LE_10B','LE_30B','GT_30B','UNKNOWN')),source_status TEXT NOT NULL DEFAULT 'SIMULATED' CHECK(source_status IN ('SIMULATED','VERIFIED')));
CREATE TABLE IF NOT EXISTS benefit_rule (rule_id TEXT PRIMARY KEY,product_id TEXT NOT NULL REFERENCES card_product(product_id),rate TEXT NOT NULL,prev_month_min INTEGER NOT NULL DEFAULT 0,min_payment INTEGER NOT NULL DEFAULT 0,per_tx_cap INTEGER,monthly_cap INTEGER,source_status TEXT NOT NULL DEFAULT 'SIMULATED');
CREATE TABLE IF NOT EXISTS benefit_rule_category (rule_id TEXT NOT NULL REFERENCES benefit_rule(rule_id),category_code TEXT NOT NULL,PRIMARY KEY(rule_id,category_code));

CREATE TABLE IF NOT EXISTS db_policy (
    policy_id TEXT PRIMARY KEY,
    monthly_applicable_amount_cap INTEGER NOT NULL,
    assume_partial_cap INTEGER NOT NULL
        CHECK(assume_partial_cap IN (0, 1)),
    assume_charge_only INTEGER NOT NULL
        CHECK(assume_charge_only IN (0, 1)),
    source_status TEXT NOT NULL DEFAULT 'SIMULATED',

    effective_from TEXT,
    effective_to TEXT,

    CHECK (
        effective_to IS NULL
        OR effective_from IS NULL
        OR effective_from < effective_to
    )
);

CREATE TABLE IF NOT EXISTS db_policy_rate (policy_id TEXT NOT NULL REFERENCES db_policy(policy_id),band_code TEXT NOT NULL,cashback_rate TEXT NOT NULL,PRIMARY KEY(policy_id,band_code));
