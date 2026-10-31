"""Upgrade a V7.2 ledger in place without losing cash postings or shift sessions."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as tmp:
        from fixture_backup_key import configure as test_backup_key
        test_backup_key(tmp)
        path=Path(tmp)/'oldledger.sqlite3'
        os.environ['RAMSES_DB_PATH']=str(path)
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='upgrade_test_owner_password_123'
        with sqlite3.connect(path) as db:
            db.executescript((ROOT/'tests/fixtures/schema_v7_2.sql').read_text())
            db.execute('INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,?,?,?,?)',('owner','placeholder','owner','2026-10-29'))
            db.execute('INSERT INTO funds(id,code,name,kind,opening_piasters) VALUES (1,?,?,?,?)',('test_cash','Test Till','cash',100000))
            db.execute('INSERT INTO shift_sessions(id,business_date,shift,fund_id,responsible_id,opened_at,opening_piasters,status,counted_piasters,expected_piasters,variance_piasters) VALUES (1,?,?,?,?,?,?,?,?,?,?)',('2026-10-29','morning',1,1,'2026-10-29T08:00:00Z',100000,'closed',105000,105000,0))
            db.execute('''INSERT INTO vouchers(id,voucher_no,date,kind,from_fund_id,shift,amount_piasters,description,status,created_by,created_at)
                      VALUES (1,?,?,?,?,?,?,?,'approved',1,?)''',('RAM-2026-000001','2026-10-29','receipt',1,'morning',5000,'Synthetic receipt for migration','2026-10-29T08:01:00Z'))
            db.execute('INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on,shift_session_id) VALUES (1,1,5000,?,1)',('2026-10-29',))
        from bootstrap import initialize,connect
        initialize()
        with connect() as db:
            assert db.execute('SELECT COUNT(*) FROM vouchers').fetchone()[0]==1
            assert db.execute('SELECT SUM(amount_piasters) FROM fund_movements').fetchone()[0]==5000
            assert db.execute('SELECT status,expected_piasters FROM shift_sessions WHERE id=1').fetchone()['expected_piasters']==105000
            assert db.execute("SELECT COUNT(*) FROM categories WHERE code IN ('cash_shortage','cash_overage')").fetchone()[0]==2
            assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('voucher_attachments','shift_variance_cases','payroll_accrual_corrections')").fetchone()[0]==3
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        with connect() as db:
            assert db.execute('SELECT COUNT(*) FROM vouchers').fetchone()[0]==1
        print('PASS — V7.2 balances and shift ledger survived V7.3 additive upgrade twice')

if __name__=='__main__':run()
