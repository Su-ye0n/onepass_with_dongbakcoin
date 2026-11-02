"""Safely align module's immutable simulation input with validated v3.4 BASE.

No generation, no DB writes. Default is read-only validation.
--apply backs up original CSV, then atomically replaces *only amount_won*.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, os, shutil, tempfile, zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

EXPECTED_COUNT=7540
EXPECTED_USERS=240
EXPECTED_AMOUNT=217449500
EXPECTED_CHANGED=175
RUN='RUN_BASE_2026-06'
SEED='seed_20261023'
DEFAULT_CSV=Path(__file__).resolve().parent/'original_transactions'/'original_base_transactions.csv'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def load_csv(path):
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames:raise ValueError('EMPTY_CSV')
        return list(reader),list(reader.fieldnames)

def get_v34(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        members=[n for n in z.namelist() if n.replace('\\','/').endswith(f'{SEED}/tx_requests.csv')]
        if len(members)!=1:raise ValueError(f'V34_SEED_MEMBER_NOT_UNIQUE: {members}')
        rows=list(csv.DictReader(io.StringIO(z.read(members[0]).decode('utf-8-sig'))))
    base=[r for r in rows if r.get('run_id')==RUN]
    if len(base)!=EXPECTED_COUNT:raise ValueError(f'V34_BASE_COUNT:{len(base)}')
    ids=[r['request_id'] for r in base]
    if len(set(ids))!=len(ids):raise ValueError('V34_DUPLICATE_REQUEST_ID')
    if len({r['user_id'] for r in base})!=EXPECTED_USERS:raise ValueError('V34_USER_COUNT_MISMATCH')
    total=sum(int(r['gross_amount_won']) for r in base)
    if total!=EXPECTED_AMOUNT:raise ValueError(f'V34_AMOUNT_MISMATCH:{total}')
    return {r['request_id']:r for r in base}

def validate(old,v34):
    required={'transaction_id','user_id','requested_at','date','event_seq','merchant_id','amount_won','lane','provider','payment_path','direct_user_card_id','scenario','seed'}
    if not old or not required.issubset(old[0]):raise ValueError('OLD_SOURCE_COLUMNS_MISSING')
    ids=[r['transaction_id'] for r in old]
    if len(ids)!=EXPECTED_COUNT or len(set(ids))!=len(ids):raise ValueError('OLD_SOURCE_ID_COUNT_OR_DUPLICATE')
    if set(ids)!=set(v34):raise ValueError('TRANSACTION_ID_SET_MISMATCH')
    mapping={'user_id':'user_id','requested_at':'request_at','event_seq':'event_seq','merchant_id':'merchant_id','lane':'payment_channel','provider':'payment_provider','payment_path':'payment_path','direct_user_card_id':'direct_user_card_id'}
    changes=[];result=[]
    for r in old:
        new=v34[r['transaction_id']]
        for old_key,new_key in mapping.items():
            if (r.get(old_key) or '').strip() != (new.get(new_key) or '').strip():
                raise ValueError(f'NON_AMOUNT_FIELD_MISMATCH:{r["transaction_id"]}:{old_key}')
        if r['date'] != new['request_at'][:10] or r['scenario']!='BASE' or r['seed']!=SEED:
            raise ValueError(f'METADATA_MISMATCH:{r["transaction_id"]}')
        before=int(r['amount_won']);after=int(new['gross_amount_won'])
        if before<=0 or after<=0:raise ValueError('NONPOSITIVE_TRANSACTION_AMOUNT')
        if before!=after:changes.append((r['transaction_id'],before,after))
        result.append({**r,'amount_won':str(after)})
    total=sum(int(r['amount_won']) for r in result)
    if total!=EXPECTED_AMOUNT:raise ValueError(f'FINAL_AMOUNT_MISMATCH:{total}')
    if len({r['user_id'] for r in result})!=EXPECTED_USERS:raise ValueError('FINAL_USER_COUNT_MISMATCH')
    # 0 changed is legitimate on a rerun, but anything other than 0/175 must be investigated.
    if len(changes) not in (0,EXPECTED_CHANGED):raise ValueError(f'UNEXPECTED_CHANGED_COUNT:{len(changes)}')
    return result,changes,total

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--zip',required=True,type=Path,help='Validated 합성데이터_v3.4_보정_전달용.zip')
    ap.add_argument('--source',default=DEFAULT_CSV,type=Path)
    ap.add_argument('--validate-only',action='store_true')
    ap.add_argument('--apply',action='store_true')
    args=ap.parse_args()
    if args.apply and args.validate_only:ap.error('Choose only one mode')
    if not args.zip.is_file():ap.error(f'ZIP_NOT_FOUND: {args.zip}')
    if not args.source.is_file():ap.error(f'SOURCE_NOT_FOUND: {args.source}')
    old,columns=load_csv(args.source)
    ref=get_v34(args.zip)
    new,changes,total=validate(old,ref)
    before=sum(int(r['amount_won']) for r in old)
    print('=== ONEPASS V3.4 SOURCE ALIGNMENT ===')
    print(f'Transactions: {len(new)} | Users: {EXPECTED_USERS}')
    print(f'Before: {before:,} won | Validated v3.4: {total:,} won')
    print(f'Amount changes required: {len(changes)} (expected: 175 if v3.3 / 0 if already v3.4)')
    print('Transaction IDs and non-amount fields: MATCH')
    if not args.apply:
        print('VALIDATION: PASSED | FILES MODIFIED: NO | DATABASE ACCESSED: NO')
        print('To apply: rerun with --apply')
        return
    if not changes:
        print('ALREADY_V34: NO FILE CHANGES')
        return
    source_hash_before=sha(args.source)
    timestamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup=args.source.with_name(f'{args.source.stem}.before_v34_{timestamp}{args.source.suffix}.bak')
    shutil.copy2(args.source,backup)
    if sha(backup)!=source_hash_before:raise ValueError('BACKUP_HASH_MISMATCH')
    tmp_path=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8-sig',newline='',dir=args.source.parent,prefix='.v34_',suffix='.tmp',delete=False) as f:
            tmp_path=Path(f.name)
            writer=csv.DictWriter(f,fieldnames=columns,extrasaction='raise')
            writer.writeheader();writer.writerows(new)
            f.flush();os.fsync(f.fileno())
        check,_=load_csv(tmp_path)
        _,check_changes,check_total=validate(check,ref)
        if check_changes or check_total!=EXPECTED_AMOUNT:raise ValueError('TEMP_VALIDATION_FAILED')
        os.replace(tmp_path,args.source)
    finally:
        if tmp_path and tmp_path.exists():tmp_path.unlink()
    report={'source':'VALIDATED_V34_BASE','seed':SEED,'run_id':RUN,'users':EXPECTED_USERS,'transactions':len(new),'total_amount_won':total,'changed_amount_count':len(changes),'zip_sha256':sha(args.zip),'source_sha256':sha(args.source),'old_sha256':source_hash_before,'backup_filename':backup.name,'other_fields_unchanged':True,'db_modified':False}
    report_path=args.source.parent/'v34_source_alignment_report.json'
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'SOURCE UPDATED: {args.source}')
    print(f'BACKUP: {backup}')
    print(f'REPORT: {report_path}')
    print('DATABASE MODIFIED: NO | SIMULATION EXECUTED: NO')

if __name__=='__main__':main()
