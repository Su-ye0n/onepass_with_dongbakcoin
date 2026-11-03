"""Read-only OnePass v3.4 result audit; no simulations or DB writes.

Default: validate experiment configuration only.
--run: validate completed four-scenario and all nine S02 result folders.
Reuses analyze_s02_sensitivity's transaction-level validation instead of
reimplementing transaction, top-up and consent reconciliation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import analyze_s02_sensitivity as analyzer

ROOT = Path(__file__).resolve().parent
DEFAULT_BASE = ROOT / 'four_scenario_analysis_v34'
DEFAULT_S02 = ROOT / 's02_sensitivity_results'
DEFAULT_INPUT = ROOT / 's02_sensitivity_inputs'
NAMES = ('S00', 'S10', 'S01', 'S11')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def audit_four_scenarios(base_dir):
    """Check all four scenarios' transaction/user aggregates and decomposition."""
    report, tx_rows, tx_index, users, fingerprint, s01_sum = analyzer.baseline_data(base_dir)
    summaries = report['summaries']
    need(set(summaries) >= set(NAMES), 'MISSING_FOUR_SCENARIO_SUMMARIES')
    for name in NAMES:
        benefit_field = f'{name}_benefit_won'
        card_field = f'{name}_selected_card'
        tx_benefit = sum(analyzer.as_int(t[benefit_field], benefit_field) for t in tx_rows)
        user_benefit = sum(analyzer.as_int(u[benefit_field], benefit_field) for u in users.values())
        summary = summaries[name]
        need(tx_benefit == user_benefit == analyzer.as_int(summary['estimated_benefit_won'], name),
             f'{name}_BENEFIT_RECONCILIATION')
        need(analyzer.as_int(summary['users'], name) == analyzer.EXPECTED_USERS,
             f'{name}_USER_COUNT')
        need(analyzer.as_int(summary['transactions'], name) == analyzer.EXPECTED_TRANSACTIONS,
             f'{name}_TX_COUNT')
        need(analyzer.as_int(summary['transaction_amount_won'], name) == analyzer.EXPECTED_AMOUNT,
             f'{name}_AMOUNT')
        db_count = sum(t[card_field] == analyzer.DB_CARD for t in tx_rows)
        need(db_count == analyzer.as_int(summary['dongbaek_count'], name), f'{name}_DB_COUNT')
        need(all(t[card_field] is not None for t in tx_rows), f'{name}_MISSING_CARD_FIELD')
    need(
        sum(analyzer.as_int(u['S11_benefit_won'], 'S11') - analyzer.as_int(u['S00_benefit_won'], 'S00')
            for u in users.values())
        == summaries['S11']['estimated_benefit_won'] - summaries['S00']['estimated_benefit_won'],
        'FOUR_SCENARIO_TOTAL_EFFECT_MISMATCH'
    )
    return report, tx_rows, tx_index, users, fingerprint, s01_sum


def audit_s02(scenarios, base, s02_dir):
    report, tx_rows, tx_index, users, fingerprint, s01_sum = base
    checked = []
    for scenario in scenarios:
        result, _details = analyzer.analyze_one(
            scenario, tx_rows, tx_index, users, fingerprint, s01_sum, s02_dir
        )
        need(result['auto_topup_total_won'] <= result['assumed_total_funding_won'],
             f"TOPUP_GREATER_THAN_ASSUMED_FUNDING:{result['scenario_id']}")
        checked.append(result)
        print(result['scenario_id'], '| benefit delta:', result['benefit_increase_won'],
              '| committed topup:', result['auto_topup_total_won'])
    need(len(checked) == 9, 'INCOMPLETE_S02_SCENARIOS')
    return checked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--baseline-dir', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--s02-results-dir', type=Path, default=DEFAULT_S02)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--validate-only', action='store_true')
    action.add_argument('--run', action='store_true', help='Audit completed result files; no simulation')
    args = parser.parse_args()
    scenarios, users = analyzer.read_manifest(args.input_dir)
    print('=== ONEPASS V3.4 RESULT AUDIT ===')
    print('Input users:', len(users), '| scenarios:', len(scenarios))
    print('CONFIGURATION: PASSED')
    if not args.run:
        print('RESULT FILES: NOT REQUIRED')
        print('SIMULATION: NOT EXECUTED')
        print('DATABASE MODIFIED: NO')
        return
    base = audit_four_scenarios(args.baseline_dir)
    need(set(base[3]) == users, 'BASELINE_USER_SET_MISMATCH')
    print('FOUR SCENARIOS: PASSED | S01 benefit:', base[5])
    checked = audit_s02(scenarios, base, args.s02_results_dir)
    print('S02 9 SCENARIOS: PASSED')
    print('TRANSACTION IDENTITY / BENEFIT / TOPUP RECONCILIATION: PASSED')
    print('AUDIT: PASSED')
    print('DATABASE MODIFIED: NO')


if __name__ == '__main__':
    main()
