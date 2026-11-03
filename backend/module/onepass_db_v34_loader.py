"""Read-only NeonDB v3.4 BASE transaction loader and compatibility adapter.

No local transaction CSV is read or changed. No DB writes.

First: python onepass_db_v34_loader.py --inspect
Then: python onepass_db_v34_loader.py --validate --table <discovered_table>
Run integration only after the DB source is validated and engine run commands are reviewed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import defaultdict,Counter
from pathlib import Path

RUN = 'RUN_BASE_2026-06'
EXPECTED_COUNT=7540
EXPECTED_SUM=217449500
EXPECTED_USERS=240
SCHEMA='public'
FIELDS={
    'request_id':'transaction_id', 'user_id':'user_id',
    'request_at':'requested_at','event_seq':'event_seq',
    'merchant_id':'merchant_id','gross_amount_won':'amount_won',
    'payment_channel':'lane','payment_provider':'provider',
    'payment_path':'payment_path','direct_user_card_id':'direct_user_card_id',
}
MANDATORY=set(FIELDS)|{'run_id'}

def discover(cur):
    cur.execute('''SELECT table_schema,table_name,column_name FROM information_schema.columns
                   WHERE table_schema = %s ORDER BY table_name,ordinal_position''',(SCHEMA,))
    found={}
    for row in cur.fetchall():
        found.setdefault(row['table_name'],set()).add(row['column_name'])
    return found

def safe_table(cur, name):
    from psycopg import sql
    cur.execute(sql.SQL('SELECT {} FROM {}.{} WHERE {}=%s ORDER BY {}, {}, {}').format(
        sql.SQL(',').join(map(sql.Identifier,sorted(MANDATORY | ({'sales_channel'})))),
        sql.Identifier(SCHEMA),sql.Identifier(name),sql.Identifier('run_id'),
        sql.Identifier('user_id'),sql.Identifier('request_at'),sql.Identifier('request_id')),(RUN,))
    return cur.fetchall()

def normalize(rows):
    grouped=defaultdict(list)
    seen=set();amount=0;providers=Counter(); lanes=Counter()
    for x in rows:
        tx={dst:x[src] for src,dst in FIELDS.items()}
        tid=str(tx['transaction_id'])
        if tid in seen:raise ValueError('DUPLICATE_REQUEST_ID:'+tid)
        seen.add(tid)
        a=int(tx['amount_won']); amount+=a
        if a<=0:raise ValueError('INVALID_AMOUNT:'+tid)
        tx['amount_won']=a
        tx['transaction_id']=tid
        tx['requested_at']=str(tx['requested_at'])
        tx['user_id']=str(tx['user_id'])
        tx['merchant_id']=str(tx['merchant_id'])
        tx['event_seq']=str(tx['event_seq']) if tx['event_seq'] is not None else '0'
        tx['provider']=tx['provider'] or None
        tx['lane']=str(tx['lane'])
        tx['date']=tx['requested_at'][:10]
        tx['scenario']='BASE';tx['seed']='seed_20261023'
        tx['sales_channel']=x.get('sales_channel')
        if tx['lane'] not in {'OFFLINE','ONLINE','SIMPLE_PAY'}:raise ValueError('INVALID_LANE:'+tid)
        if (tx['lane']=='SIMPLE_PAY')!=bool(tx['provider']):raise ValueError('INVALID_PROVIDER:'+tid)
        if tx['requested_at'][:7]!='2026-06':raise ValueError('INVALID_MONTH:'+tid)
        grouped[tx['user_id']].append(tx)
        lanes[tx['lane']]+=1
        if tx['provider']:providers[str(tx['provider'])]+=1
    for arr in grouped.values():arr.sort(key=lambda t:(t['requested_at'],int(t['event_seq']),t['transaction_id']))
    if len(rows)!=EXPECTED_COUNT:raise ValueError(f'TX_COUNT_MISMATCH:{len(rows)}')
    if len(grouped)!=EXPECTED_USERS:raise ValueError(f'USER_COUNT_MISMATCH:{len(grouped)}')
    if amount!=EXPECTED_SUM:raise ValueError(f'TOTAL_AMOUNT_MISMATCH:{amount}')
    return grouped,{'users':len(grouped),'transactions':len(rows),'amount_won':amount,
                    'lanes':dict(lanes),'providers':dict(providers),'run_id':RUN}

def load(table=None,inspect_only=False):
    from onepass.db_connection import connect_readonly
    with connect_readonly() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            tables=discover(cur)
            candidates={n:len(MANDATORY & cols) for n,cols in tables.items() if 'run_id' in cols}
            if inspect_only:
                print('=== NEONDB TRANSACTION TABLE INSPECTION ===')
                print('Run:',RUN)
                for n,match in sorted(candidates.items(),key=lambda v:-v[1]):
                    print(f'{n}: {match}/{len(MANDATORY)} needed columns; missing:',
                          ', '.join(sorted(MANDATORY-tables[n])) or '-')
                if not candidates:print('NO_TABLE_WITH_RUN_ID: data-team confirmation needed')
                conn.rollback();return None,None
            if table:
                if table not in tables:raise ValueError('TABLE_NOT_IN_PUBLIC_SCHEMA:'+table)
            else:
                eligible=[n for n,cols in tables.items() if MANDATORY.issubset(cols) and 'sales_channel' in cols]
                if len(eligible)!=1:raise ValueError('AMBIGUOUS_SOURCE_TABLE: use --inspect then --table; options='+repr(eligible))
                table=eligible[0]
            need=MANDATORY | {'sales_channel'}
            missing=need-tables[table]
            if missing:raise ValueError('SOURCE_COLUMNS_MISSING:'+','.join(sorted(missing)))
            rows=safe_table(cur,table)
            grouped,stats=normalize(rows)
            stats['source_table']=SCHEMA+'.'+table
            # verify the merchant rows that engine reads exist (does not establish 105 upgrades)
            ids=sorted({tx['merchant_id'] for ts in grouped.values() for tx in ts})
            cur.execute('SELECT merchant_id FROM public.merchant WHERE merchant_id=ANY(%s)',(ids,))
            present={str(r['merchant_id']) for r in cur.fetchall()}
            if present!=set(ids):raise ValueError('DB_MERCHANTS_MISSING:'+str(len(set(ids)-present)))
            stats['referenced_merchants']=len(ids)
            conn.rollback()
            return grouped,stats

def main():
    p=argparse.ArgumentParser(description=__doc__)
    action=p.add_mutually_exclusive_group(required=True)
    action.add_argument('--inspect',action='store_true')
    action.add_argument('--validate',action='store_true')
    p.add_argument('--table',help='Exact public table name verified using --inspect')
    args=p.parse_args()
    if args.inspect:load(inspect_only=True);return
    grouped,stats=load(args.table)
    print('=== NEONDB V3.4 BASE VALIDATION ===')
    print(json.dumps(stats,ensure_ascii=False,indent=2))
    print('VALIDATION: PASSED')
    print('DATABASE MODIFIED: NO')
    print('LOCAL CSV MODIFIED: NO')
    print('SIMULATION: NOT EXECUTED')

if __name__=='__main__':main()
