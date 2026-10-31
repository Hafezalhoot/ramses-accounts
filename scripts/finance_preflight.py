"""Offline read-only accounting checks, not a substitute for a hospital audit.

Reports control-ledger differences without mutating a production or test DB.
For an isolated database copy use: python scripts/finance_preflight.py --db ... --period YYYY-MM
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from ledger import trial_balance
from financial_integrity import patient_reconciliation
from treasury_integrity import treasury_reconciliation


def run(db_path:Path, month:str):
    try:
        if len(month)!=7 or month[4]!='-' or date.fromisoformat(month+'-01').strftime('%Y-%m')!=month:
            raise ValueError('Period must be a valid YYYY-MM')
    except ValueError:
        raise ValueError('Period must be a valid YYYY-MM') from None
    if not db_path.is_file():
        raise ValueError('SQLite source does not exist; refusing to create empty database')
    with sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',uri=True,timeout=20) as c:
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA query_only=ON')
        sql_integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        fk_violations=len(c.execute('PRAGMA foreign_key_check').fetchall())
        ledger=trial_balance(c,month)
        patients=patient_reconciliation(c,month)
        treasury=treasury_reconciliation(c,month)
        flags=[]
        if sql_integrity!='ok':flags.append('sqlite_corruption')
        if fk_violations:flags.append('foreign_key_violation')
        if not ledger['balanced']:flags.append('trial_balance_unbalanced')
        if not patients['matched']:flags.append('patient_subledger_difference')
        if not treasury['matched']:flags.append('treasury_control_difference')
        return {'period':month,'generated_utc':datetime.now(timezone.utc).isoformat(),
                'status':'PASS' if not flags else 'FAIL','issues':flags,
                'sqlite_integrity_ok':sql_integrity=='ok','foreign_key_violations':fk_violations,
                'trial_balance_balanced':ledger['balanced'],
                'patient_checks':[{k:r[k] for k in ('code','expected_piasters','ledger_piasters','difference_piasters','matched')}
                                  for r in patients['checks']],
                'patient_reconciliation_ok':patients['matched'],
                'treasury_issue_count':treasury['issue_count'],
                'treasury_issue_types':sorted({item['type'] for item in treasury['issues']}),
                'treasury_reconciliation_ok':treasury['matched'],
                'scope':'Read-only ledger controls only; does not certify physical money, clinical billing, backups or full ERP release readiness.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,required=True)
    p.add_argument('--period',required=True)
    args=p.parse_args(argv)
    try:
        report=run(args.db,args.period)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report['status']=='PASS' else 2
    except (ValueError,sqlite3.Error) as error:
        print(json.dumps({'status':'ERROR','error':str(error)},ensure_ascii=False))
        return 3


if __name__=='__main__':
    raise SystemExit(main())
