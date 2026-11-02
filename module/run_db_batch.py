"""Load reference data and policy from SQLite, then execute the original batch logic."""
import argparse, json
from pathlib import Path
from onepass.repository import CatalogRepository
from onepass.batch import run_batch

def main():
    root=Path(__file__).resolve().parent
    p=argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=root/'data'/'demo_catalog.sqlite')
    p.add_argument('--requests',type=Path,default=root/'data'/'tx_requests.csv')
    p.add_argument('--output',type=Path,default=root/'output_db')
    p.add_argument('--run-id',default='DB-DEMO-001')
    p.add_argument('--policy-id',default='SIM_POLICY_01')
    a=p.parse_args()
    if not a.db.exists(): raise SystemExit(f'DB missing: {a.db}; first run python db/seed.py')
    repo=CatalogRepository(a.db)
    # Inject the actual DB-loaded policy, not a hardcoded default.
    result=run_batch(None,a.requests,a.output,a.run_id,loaded=repo.load(a.policy_id))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
