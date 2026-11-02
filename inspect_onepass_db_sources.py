"""Safe read-only NeonDB schema inventory for OnePass v3.4.

No local CSV, database writes, or simulations. Avoids printing row contents.
"""
from __future__ import annotations
import argparse
from collections import defaultdict

TOKENS = ('transaction','request','payment','original','synthetic','merchant','run','batch','v34','tx_','source')
CORE = {'request_id','transaction_id','tx_id','user_id','merchant_id','run_id','gross_amount_won','amount_won','requested_at','request_at','payment_channel','lane','industry_code','sales_band'}

def inspect():
    from onepass.db_connection import connect_readonly
    from psycopg import sql
    with connect_readonly() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cur.execute('''SELECT table_schema, table_name, column_name
                           FROM information_schema.columns
                           WHERE table_schema NOT IN ('information_schema','pg_catalog')
                           ORDER BY table_schema,table_name,ordinal_position''')
            tables=defaultdict(list)
            for r in cur.fetchall():
                tables[(r['table_schema'],r['table_name'])].append(r['column_name'])
            print('=== ONEPASS DB SOURCE INVENTORY (READ ONLY) ===')
            print('Visible tables/views:',len(tables))
            candidates=[]
            for (schema,name),cols in tables.items():
                colset=set(cols)
                score=4*len(colset & {'request_id','transaction_id','tx_id'})+2*len(colset & {'merchant_id','user_id','run_id','amount_won','gross_amount_won'})
                score+=sum(1 for token in TOKENS if token in name.lower())
                if score>=3: candidates.append((score,schema,name,cols))
            candidates.sort(key=lambda x:(-x[0],x[1],x[2]))
            if not candidates: print('No transaction-like table visible to this DB connection.')
            for score,schema,name,cols in candidates[:40]:
                label=f'{schema}.{name}'
                print('\nTABLE:',label, '| match_score:',score)
                print('MATCHED COLUMNS:',', '.join(sorted(set(cols)&CORE)) or '(none)')
                print('ALL COLUMNS:',', '.join(cols[:55]) + (' ...' if len(cols)>55 else ''))
                try:
                    cur.execute(sql.SQL('SELECT COUNT(*) AS n FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(name)))
                    print('ROWS:',int(cur.fetchone()['n']))
                except Exception as e:
                    print('COUNT UNAVAILABLE:',type(e).__name__)
                    conn.rollback()
                    cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            print('\nINSPECTION ONLY. NO ROW VALUES DISPLAYED.')
            print('DATABASE MODIFIED: NO')
            conn.rollback()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inspect',action='store_true',required=True)
    p.parse_args()
    inspect()
