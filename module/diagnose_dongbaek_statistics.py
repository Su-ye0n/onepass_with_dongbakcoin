"""Read-only comparison of OnePass V2 synthetic data with the 2025 Dongbaekjeon survey.

This does NOT mistake all-card transactions for observed Dongbaek payments.
The survey's usage statistics have a different measurement basis.
No database connections, uploads or simulations.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / 'v2_output' / 'sim_user_profile_v2.csv'
TRANSACTIONS = ROOT / 'original_transactions' / 'original_base_transactions.csv'
OUTPUT = ROOT / 'dongbaek_statistics_diagnostic.json'

# 부산 지역화폐 '동백전'의 지역경제 기여도 및 정책 개선방안,
# 2025년 6~8월 동백전 가입자 1,000명 대상 설문.
SURVEY = {
    'monthly_usage_won': {'2025-06': 172000, '2025-07': 177000, '2025-08': 181000},
    'monthly_usage_100k_to_under_300k_pct': 28.8,
    'at_least_weekly_use_pct': 62.1,
    'almost_never_use_pct': 20.5,
    'transaction_10k_to_under_30k_pct': 45.4,
    'transaction_under_50k_pct': 89.6,
    'continue_recharging_after_cashback_cap_pct': 38.4,
    'usage_by_age_2025_08_won': {
        '18~29': 111000, '30s': 175000, '40s': 225000,
        '50s': 189000, '60+': 192000,
    },
    'most_used_places_pct': {
        'restaurant': 27.4, 'grocery': 18.1, 'cafe_bakery': 14.4,
        'convenience': 12.6, 'hospital_pharmacy': 10.7,
    },
}


def rows(path):
    if not path.is_file():
        raise FileNotFoundError(f'FILE_NOT_FOUND:{path}')
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f'EMPTY_OR_INVALID_CSV:{path}')
        return list(reader)


def require_columns(data, columns, label):
    if not data or not columns.issubset(data[0]):
        raise ValueError(f'INVALID_{label}_COLUMNS:{sorted(columns)}')


def pct(n, d):
    return round(100 * n / d, 2) if d else None


def summarize_amounts(amounts):
    if not amounts:
        return {'count': 0}
    ordered = sorted(amounts)
    return {
        'count': len(amounts),
        'sum_won': sum(amounts),
        'mean_won': round(mean(amounts), 2),
        'median_won': median(amounts),
        'below_10000_pct': pct(sum(x < 10000 for x in amounts), len(amounts)),
        '10000_to_under_30000_pct': pct(sum(10000 <= x < 30000 for x in amounts), len(amounts)),
        'under_50000_pct': pct(sum(x < 50000 for x in amounts), len(amounts)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profiles', type=Path, default=PROFILE)
    parser.add_argument('--transactions', type=Path, default=TRANSACTIONS)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()

    profiles = rows(args.profiles)
    txs = rows(args.transactions)
    require_columns(profiles, {'user_id','age_band','dongbaek_usage_level','original_month_spend_won'}, 'PROFILE')
    require_columns(txs, {'user_id','transaction_id','requested_at','amount_won','lane'}, 'TRANSACTION')
    by_uid = {}
    for p in profiles:
        uid = p['user_id'].strip()
        if not uid or uid in by_uid:
            raise ValueError(f'INVALID_OR_DUPLICATE_PROFILE_USER:{uid}')
        by_uid[uid] = p
    tx_users = {t['user_id'].strip() for t in txs}
    if set(by_uid) != tx_users:
        raise ValueError('PROFILE_TRANSACTION_USER_COVERAGE_MISMATCH')
    ids = [t['transaction_id'] for t in txs]
    if len(ids) != len(set(ids)):
        raise ValueError('DUPLICATE_TRANSACTION_IDS')
    if len(by_uid) != 240 or len(txs) != 7540:
        raise ValueError(f'UNEXPECTED_POPULATION:{len(by_uid)}:{len(txs)}')

    members = {uid for uid,p in by_uid.items() if p['dongbaek_usage_level'] != 'NON_MEMBER'}
    if len(members) != 111:
        raise ValueError(f'UNEXPECTED_MEMBER_COUNT:{len(members)}')
    current_months = {t['requested_at'][:7] for t in txs}
    if current_months != {'2026-06'}:
        raise ValueError(f'UNEXPECTED_TRANSACTION_MONTHS:{current_months}')

    all_amounts = []
    member_amounts = []
    member_offline_amounts = []
    lane_counts = Counter()
    days_by_user = defaultdict(set)
    member_days_by_user = defaultdict(set)
    tx_by_user = Counter()
    for t in txs:
        uid = t['user_id'].strip()
        amount = int(t['amount_won'])
        if amount <= 0:
            raise ValueError('INVALID_TRANSACTION_AMOUNT')
        day = date.fromisoformat(t['requested_at'][:10])
        all_amounts.append(amount)
        lane_counts[t['lane']] += 1
        days_by_user[uid].add(day)
        tx_by_user[uid] += 1
        if uid in members:
            member_amounts.append(amount)
            member_days_by_user[uid].add(day)
            if t['lane'] == 'OFFLINE':
                member_offline_amounts.append(amount)

    level_counts = Counter(by_uid[uid]['dongbaek_usage_level'] for uid in members)
    age_counts = Counter(by_uid[uid]['age_band'] for uid in members)
    prev_spend = [int(p['original_month_spend_won']) for p in profiles]
    member_prev_spend = [int(by_uid[uid]['original_month_spend_won']) for uid in members]
    # Only an all-card usage-frequency indicator. NOT a Dongbaek-use-frequency estimate.
    days_30 = [len(days_by_user[uid]) for uid in by_uid]
    member_days_30 = [len(member_days_by_user[uid]) for uid in members]
    result = {
        'source': '부산 지역화폐 동백전의 지역경제 기여도 및 정책 개선방안',
        'observed_survey': SURVEY,
        'population': {'users':len(by_uid), 'dongbaek_members':len(members), 'nonmembers':len(by_uid)-len(members), 'transaction_count':len(txs), 'transaction_month':'2026-06'},
        'v2_profile': {
            'dongbaek_usage_level_distribution_members_only':dict(sorted(level_counts.items())),
            'member_age_distribution':dict(sorted(age_counts.items())),
            'previous_month_all_card_spend_all_users': summarize_amounts(prev_spend),
            'previous_month_all_card_spend_members':summarize_amounts(member_prev_spend),
            'note':'original_month_spend_won is ALL-CARD spend, NOT observed Dongbaek spend.',
        },
        'original_transactions_all_cards': {
            'amounts': summarize_amounts(all_amounts),
            'payment_lane_counts':dict(sorted(lane_counts.items())),
            'mean_distinct_payment_days_per_user':round(mean(days_30),2),
            'at_least_four_distinct_payment_days_pct':pct(sum(x>=4 for x in days_30),len(days_30)),
            'note':'All cards only. Four payment dates/month is NOT the same as Dongbaek weekly use.',
        },
        'original_transactions_dongbaek_members_all_cards': {
            'amounts':summarize_amounts(member_amounts),
            'offline_lanes_amounts':summarize_amounts(member_offline_amounts),
            'mean_distinct_payment_days_per_member':round(mean(member_days_30),2),
            'at_least_four_distinct_payment_days_pct':pct(sum(x>=4 for x in member_days_30),len(member_days_30)),
            'note':'These are ALL-CARD transactions by members, NOT Dongbaek payments or confirmed eligible merchants.',
        },
        'direct_survey_comparisons': {
            'dongbaek_monthly_usage':{'status':'NOT_IDENTIFIABLE','reason':'No observed Dongbaek-selected transaction history in original data.'},
            'dongbaek_age_specific_usage':{'status':'NOT_IDENTIFIABLE','reason':'Age exists, but Dongbaek-specific spend is not observed.'},
            'dongbaek_per_transaction_amount':{'status':'NOT_IDENTIFIABLE','reason':'Transaction amounts are for all cards.'},
            'dongbaek_weekly_frequency':{'status':'NOT_IDENTIFIABLE','reason':'Only all-card transaction dates are observed.'},
            'dongbaek_spending_merchant_category':{'status':'NOT_IDENTIFIABLE','reason':'Merchant ID has no industry mapping in this input, and card paid is not observed.'},
            'auto_topup_consent':{'status':'NOT_OBSERVED','reason':'38.4% is continued recharging after cashback-cap depletion, not auto-topup consent.'},
            'funding_balance':{'status':'NOT_OBSERVED','reason':'Monthly usage does not measure available bank account funding.'},
        },
        'simulation_recommendation':'Keep V2 source transactions and slot assignments unchanged pending an actual Dongbaek-specific outcome dataset. Use survey statistics as external anchors, not calibration targets for all-card transactions.',
        'database_modified':False,
        'simulation_executed':False,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

    print('=== DONGBAEK STATISTICS DIAGNOSTIC ===')
    print('Users:',len(by_uid),'| Members:',len(members),'| Transactions:',len(txs))
    print('All-card tx amount:',sum(all_amounts))
    print('All-card transaction 10k-30k (%):',result['original_transactions_all_cards']['amounts']['10000_to_under_30000_pct'])
    print('All-card transaction under 50k (%):',result['original_transactions_all_cards']['amounts']['under_50000_pct'])
    print('Member all-card tx under 50k (%):',result['original_transactions_dongbaek_members_all_cards']['amounts']['under_50000_pct'])
    print('Member usage levels:',dict(sorted(level_counts.items())))
    print('Survey Dongbaek tx under 50k (%):',SURVEY['transaction_under_50k_pct'])
    print('DIRECT COMPARABILITY: NOT AVAILABLE (different payment populations)')
    print('DIAGNOSTIC: PASSED')
    print('DATABASE MODIFIED: NO')
    print('SIMULATION: NOT EXECUTED')
    print('Saved:',args.output)

if __name__ == '__main__':
    main()
