"""V7.1 -> V7.2 upgrade preserves existing postings and enables shift linkage."""
import os
import sys
import sqlite3
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as temp:
        database=Path(temp)/'previous.sqlite3'
        os.environ['RAMSES_DB_PATH']=str(database)
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='migration_test_secret_123456'
        from fixture_backup_key import configure as test_backup_key
        test_backup_key(temp)
        # Synthetic historical V7.1-shaped ledger: a complete recognized
        # source with a real voucher/fund, but no shift_session_id yet.
        with sqlite3.connect(database) as c:
            c.executescript((ROOT/'tests/fixtures/schema_v7_2.sql').read_text())
            c.execute('ALTER TABLE fund_movements DROP COLUMN shift_session_id')
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,'owner','test_hash','owner','2026-10-05')")
            c.execute("INSERT INTO funds(id,code,name,kind) VALUES (1,'synthetic_cash','Synthetic cash till','cash')")
            c.execute("""INSERT INTO vouchers(id,voucher_no,date,kind,from_fund_id,shift,amount_piasters,
                description,status,created_by,created_at) VALUES
                (4,'TEST-V71-004','2026-10-05','receipt',1,'morning',12500,
                 'Synthetic historical receipt','approved',1,'2026-10-05')""")
            c.execute("INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on) VALUES (4,1,12500,'2026-10-05')")
        from bootstrap import initialize,connect
        initialize()
        with connect() as c:
            columns={r['name'] for r in c.execute('PRAGMA table_info(fund_movements)')}
            assert 'shift_session_id' in columns
            r=c.execute('SELECT voucher_id,fund_id,amount_piasters,booked_on,shift_session_id FROM fund_movements').fetchone()
            assert r['voucher_id']==4 and r['amount_piasters']==12500 and r['shift_session_id'] is None
            assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='shift_sessions'").fetchone()[0]==1
        initialize()
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==1
        print('PASS — upgrade adds shift link without deleting or changing historical live postings')

if __name__=='__main__':run()
