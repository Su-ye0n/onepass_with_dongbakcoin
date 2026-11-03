
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from onepass.m1_parameters import load_handoff
from db.migrate_s1_3 import migrate, find_rules_at


def csvout(root, name, rows):
    with (root/name).open('w', newline='', encoding='utf8') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def test_m1_valid_handoff(tmp_path):
    csvout(tmp_path, 'age_district_weights.csv', [{'age_band':'20s','district_code':'26110','weight':'1'}])
    csvout(tmp_path, 'age_category_weights.csv', [{'age_band':'20s','source_category_code':'CS100010','weight':'1','reference_period':'2025Q2'}])
    csvout(tmp_path, 'category_crosswalk.csv', [{'source_category_code':'CS100010','engine_category':'CAFE','mapping_status':'CONFIRMED'}])
    csvout(tmp_path, 'category_ticket_means.csv', [{'source_category_code':'CS100010','mean_ticket_won':'8000'}])
    csvout(tmp_path, 'spend_band_weights.csv', [{'metric':'MONTHLY_SPEND','band_code':'LT100','weight':'1','respondent_scope':'ALL'}])
    csvout(tmp_path, 'dongbaek_usage_weights.csv', [{'metric':'DB_MONTHLY_USE','band_code':'0','weight':'1','respondent_scope':'MEMBERS'}])
    csvout(tmp_path, 'card_ownership_weights.csv', [{'combination_code':'CREDIT_ONLY','weight':'1'}])
    assert len(load_handoff(tmp_path).tables)==7


def test_s13_migration_idempotent_and_half_open(tmp_path):
    db_path=tmp_path/'demo.db'
    with sqlite3.connect(db_path) as db:
        db.execute('CREATE TABLE benefit_rule (rule_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, rate TEXT NOT NULL)')
        db.execute("INSERT INTO benefit_rule VALUES ('R1','P1','0.05')")
    migrate(db_path); migrate(db_path)
    with sqlite3.connect(db_path) as db:
        assert len(find_rules_at(db,'P1','2026-07-01'))==1
        db.execute("UPDATE benefit_rule SET effective_from='2026-07-01', effective_to='2026-08-01' WHERE rule_id='R1'")
        assert len(find_rules_at(db,'P1','2026-07-31'))==1
        assert len(find_rules_at(db,'P1','2026-08-01'))==0
