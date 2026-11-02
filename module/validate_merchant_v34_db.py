"""Read-only verification of v3.4 merchant industry corrections against NeonDB.

Usage (from module directory):
  python validate_merchant_v34_db.py --zip "합성데이터_v3.4_보정_전달용.zip"

Reads ZIP reference and public.merchant using existing onepass.db_connection.
Never writes to DB or modifies CSV files. Requires psycopg and python-dotenv.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

EXPECTED_MERCHANTS = 1677
EXPECTED_CHANGES = 105
SEEDS = ("seed_20261023", "seed_20262023", "seed_20263023")


def read_csv_from_zip(zf, seed, suffix):
    target = f"csv\\{seed}\\{suffix}"
    names = {s.replace('/', '\\'): s for s in zf.namelist()}
    if target not in names:
        raise ValueError(f"MISSING_ZIP_MEMBER: {target}")
    data = zf.read(names[target]).decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(data)))


def key_by(rows, field, label):
    values = [str(r[field]).strip() for r in rows]
    duplicates = [k for k, n in Counter(values).items() if n > 1]
    if duplicates or any(not v for v in values):
        raise ValueError(f"INVALID_OR_DUPLICATE_IDS_{label}: {duplicates[:10]}")
    return dict(zip(values, rows))


def reference_data(zip_path):
    references = {}
    with zipfile.ZipFile(zip_path) as zf:
        for seed in SEEDS:
            merchant = key_by(read_csv_from_zip(zf, seed, 'MERCHANT.csv'), 'merchant_id', f'MERCHANT_{seed}')
            changes = key_by(read_csv_from_zip(zf, seed, '_aux\\FIX_V34_MERCHANT_LOG.csv'), 'merchant_id', f'LOG_{seed}')
            if len(merchant) != EXPECTED_MERCHANTS:
                raise ValueError(f'INVALID_REFERENCE_MERCHANT_COUNT_{seed}: {len(merchant)}')
            values = {k: str(v['industry_code']).strip() for k, v in merchant.items()}
            updates = {k: (str(v['old_industry_code']).strip(), str(v['new_industry_code']).strip()) for k, v in changes.items()}
            for mid, (old, new) in updates.items():
                if mid not in values or values[mid] != new or old == new:
                    raise ValueError(f'INCONSISTENT_REFERENCE_{seed}: {mid}')
            references[seed] = (values, updates)
    return references


def verify(zip_path):
    references = reference_data(zip_path)
    from onepass.db_connection import connect_readonly
    with connect_readonly() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT merchant_id, industry_code FROM public.merchant')
            rows = cur.fetchall()
        conn.rollback()
    db = key_by(rows, 'merchant_id', 'DB_MERCHANT')
    actual = {k: str(v['industry_code']).strip() if v['industry_code'] is not None else '' for k, v in db.items()}
    results = {}
    for seed, (ref, updates) in references.items():
        missing = sorted(set(ref) - set(actual))
        extra = sorted(set(actual) - set(ref))
        mismatches = [dict(merchant_id=k, expected=ref[k], db=actual[k], in_change_log=k in updates)
                      for k in sorted(set(ref) & set(actual)) if ref[k] != actual[k]]
        changed_ok = sum(1 for k, (_, new) in updates.items() if actual.get(k) == new)
        old_left = [k for k, (old, _) in updates.items() if actual.get(k) == old]
        passed = not missing and not extra and not mismatches and len(actual) == EXPECTED_MERCHANTS and changed_ok == len(updates)
        results[seed] = dict(match=passed, expected_merchants=len(ref), db_merchants=len(actual),
                             expected_industry_changes=len(updates), changed_merchants_matching=changed_ok,
                             all_industry_matching=len(ref) - len(missing) - len(mismatches),
                             missing_merchant_ids=missing, unexpected_merchant_ids=extra,
                             changes_still_on_old_code=old_left, industry_mismatches=mismatches)
    matches = [seed for seed, result in results.items() if result['match']]
    return dict(status='PASS' if len(matches) == 1 else ('AMBIGUOUS_MULTIPLE_MATCHES' if len(matches) > 1 else 'NO_EXACT_SEED_MATCH'),
                matching_seeds=matches, seed_results=results, db_modified=False, local_source_modified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', required=True, dest='zip_path', type=Path)
    parser.add_argument('--report', type=Path, help='Optional local JSON report destination (not a DB write)')
    args = parser.parse_args()
    try:
        outcome = verify(args.zip_path)
        print('=== ONEPASS V3.4 MERCHANT DB VERIFICATION (READ ONLY) ===')
        for seed, result in outcome['seed_results'].items():
            print(f"{seed}: {result['all_industry_matching']}/{result['expected_merchants']} industry codes match; "
                  f"correction log {result['changed_merchants_matching']}/{result['expected_industry_changes']}; "
                  f"missing {len(result['missing_merchant_ids'])}, extra {len(result['unexpected_merchant_ids'])}")
            for item in result['industry_mismatches'][:5]:
                print('  MISMATCH:', item['merchant_id'], 'expected=', item['expected'], 'db=', item['db'])
        print('MATCHING SEEDS:', ', '.join(outcome['matching_seeds']) or 'NONE')
        print('STATUS:', outcome['status'])
        print('DATABASE MODIFIED: NO')
        if args.report:
            args.report.write_text(json.dumps(outcome, indent=2, ensure_ascii=False), encoding='utf-8')
            print('REPORT:', args.report)
        return 0 if outcome['status'] == 'PASS' else 2
    except Exception as exc:
        print('VERIFICATION ERROR:', type(exc).__name__, str(exc))
        print('DATABASE MODIFIED: NO')
        return 1

if __name__ == '__main__':
    sys.exit(main())
