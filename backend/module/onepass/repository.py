"""Read-only SQLite catalog adapter for v0.2-compatible rule-engine DTOs.

Simulation only. No actual payment processing. In a v0.7 codebase this module
can be reused, while the wrapper in run_db_batch.py may require adjustment.
"""

from __future__ import annotations
from contextlib import closing
import sqlite3
from decimal import Decimal
from pathlib import Path
from .engine import Card, CardType, BenefitRule, Merchant, DbPolicy, State

class UnsupportedCatalogValue(ValueError):
    pass

class CatalogRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    
    def load_policy_at(
        self,
        transaction_date: str,
        policy_id: str | None = None
    ) -> DbPolicy:
        """
        거래일(YYYY-MM-DD)에 유효한 정책을 조회한다.

        기간 규칙:
        effective_from <= transaction_date < effective_to

        effective_to가 NULL이면 종료일 제한이 없다.
        해당 정책이 없거나 중복되면 실행을 중단한다.
        """

        from datetime import date

        try:
            transaction_date = date.fromisoformat(
                transaction_date
            ).isoformat()
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid transaction_date: {transaction_date}"
            ) from exc

        with closing(self.connect()) as db:
            query = """
                SELECT *
                FROM db_policy
                WHERE effective_from <= ?
                  AND (
                      effective_to IS NULL
                      OR ? < effective_to
                  )
            """

            params = [
                transaction_date,
                transaction_date,
            ]

            if policy_id is not None:
                query += " AND policy_id = ?"
                params.append(policy_id)

            rows = db.execute(
                query, params
            ).fetchall()

            if not rows:
                raise ValueError(
                    f"No effective DB policy for "
                    f"{transaction_date}"
                )

            if len(rows) > 1:
                raise ValueError(
                    f"Multiple effective DB policies for "
                    f"{transaction_date}: "
                    f"{[r['policy_id'] for r in rows]}"
                )

            p = rows[0]

            rate_rows = db.execute(
                """
                SELECT band_code, cashback_rate
                FROM db_policy_rate
                WHERE policy_id = ?
                """,
                (p["policy_id"],)
            ).fetchall()

            if not rate_rows:
                raise ValueError(
                    f"No cashback rates for policy "
                    f"{p['policy_id']}"
                )

            rates = {
                r["band_code"]: Decimal(r["cashback_rate"])
                for r in rate_rows
            }

            return DbPolicy(
                cashback_rates=rates,
                monthly_applicable_amount_cap=(
                    p["monthly_applicable_amount_cap"]
                ),
                assume_partial_cap=bool(
                    p["assume_partial_cap"]
                ),
                assume_cashback_eligible_charge_only=bool(
                    p["assume_charge_only"]
                ),
            )

    def load(self, policy_id: str = 'SIM_POLICY_01'):
        with closing(self.connect()) as db:
            p = db.execute('SELECT * FROM db_policy WHERE policy_id=?', (policy_id,)).fetchone()
            if p is None:
                raise ValueError(f'Unknown policy: {policy_id}')
            rates = {r['band_code']: Decimal(r['cashback_rate']) for r in db.execute('SELECT band_code,cashback_rate FROM db_policy_rate WHERE policy_id=?',(policy_id,))}
            policy = DbPolicy(cashback_rates=rates,monthly_applicable_amount_cap=p['monthly_applicable_amount_cap'],assume_partial_cap=bool(p['assume_partial_cap']),assume_cashback_eligible_charge_only=bool(p['assume_charge_only']))
            merchants = {}
            for r in db.execute('SELECT * FROM merchant'):
                if r['db_registration_status'] == 'UNKNOWN':
                    continue  # explicitly not passed as FALSE to the v0.2 boolean engine
                if r['annual_sales_band'] == 'UNKNOWN':
                    continue  # do not silently zero-out cashback
                if r['annual_sales_band'] not in rates:
                    raise UnsupportedCatalogValue(f"merchant {r['merchant_id']}: unknown band {r['annual_sales_band']}")
                merchants[r['merchant_id']] = Merchant(r['merchant_id'],r['category_code'],r['db_registration_status']=='REGISTERED',r['annual_sales_band'])
            users = {}
            for row in db.execute('SELECT user_id,db_charge,db_cashback,db_grant,db_month_applied FROM sim_user ORDER BY user_id'):
                uid = row['user_id']
                accounts = {a['account_id']:a['opening_balance_won'] for a in db.execute('SELECT account_id,opening_balance_won FROM funding_account WHERE user_id=?',(uid,))}
                cards=[]
                for c in db.execute('SELECT * FROM user_card WHERE user_id=? ORDER BY user_card_id',(uid,)):
                    prod=db.execute('SELECT * FROM card_product WHERE product_id=?',(c['product_id'],)).fetchone()
                    if prod is None: raise ValueError(f'Missing product for {c["user_card_id"]}')
                    try: ctype=CardType(prod['engine_type'])
                    except ValueError as exc: raise UnsupportedCatalogValue(f'unsupported card type: {prod["engine_type"]}') from exc
                    rules=[]
                    for r in db.execute('SELECT * FROM benefit_rule WHERE product_id=? ORDER BY rule_id',(c['product_id'],)):
                        cats = tuple(x['category_code'] for x in db.execute('SELECT category_code FROM benefit_rule_category WHERE rule_id=? ORDER BY category_code',(r['rule_id'],)))
                        rules.append(BenefitRule(id=f"{c['user_card_id']}:{r['rule_id']}",categories=cats,rate=Decimal(r['rate']),prev_month_min=r['prev_month_min'],min_payment=r['min_payment'],per_tx_cap=r['per_tx_cap'],monthly_cap=r['monthly_cap']))
                    cards.append(Card(id=c['user_card_id'],type=ctype,account_id=c['account_id'],credit_limit=c['credit_limit'],active=bool(c['active']),lost=bool(c['lost']),expired=bool(c['expired']),prev_month_perf=c['prev_month_perf'],rules=tuple(rules)))
                users[uid]=(cards,State(accounts=accounts,credit_used={},db_charge=row['db_charge'],db_cashback=row['db_cashback'],db_grant=row['db_grant'],db_month_applied=row['db_month_applied']))
        return merchants,users,policy

    def export_legacy_config(self, policy_id='SIM_POLICY_01'):
        """Compatibility with v0.2 batch runner. Keeps missing / unknown explicit."""
        from dataclasses import asdict
        merchants,users,_=self.load(policy_id)
        result={'merchants':[{'id':m.id,'category':m.category,'db_registered':m.db_registered,'annual_sales_band':m.annual_sales_band} for m in merchants.values()],'users':[]}
        for uid,(cards,s) in users.items():
            result['users'].append({'user_id':uid,'cards':[{'id':c.id,'type':c.type.value,'account_id':c.account_id,'credit_limit':c.credit_limit,'active':c.active,'lost':c.lost,'expired':c.expired,'prev_month_perf':c.prev_month_perf,'rules':[{'id':r.id,'categories':list(r.categories),'rate':str(r.rate),'prev_month_min':r.prev_month_min,'min_payment':r.min_payment,'per_tx_cap':r.per_tx_cap,'monthly_cap':r.monthly_cap} for r in c.rules]} for c in cards],'initial_state':{'accounts':s.accounts,'credit_used':s.credit_used,'db_charge':s.db_charge,'db_cashback':s.db_cashback,'db_grant':s.db_grant,'db_month_applied':s.db_month_applied}})
        return result
