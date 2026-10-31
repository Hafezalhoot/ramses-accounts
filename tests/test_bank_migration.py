"""V7.5 to V7.6 upgrade must not alter or auto-match existing bank movements."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as td:
        from fixture_backup_key import configure as test_backup_key
        test_backup_key(td)
        path=Path(td)/'existing.sqlite3'
        os.environ['RAMSES_DB_PATH']=str(path)
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_upgrade_test_pw_123456'
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript((ROOT/'tests/fixtures/schema_v7_5.sql').read_text())
            db.execute('''INSERT INTO users(id,username,password_hash,role,created_at)
                         VALUES (1,'owner','test_hash','owner','2026-10-01')''')
            db.execute("INSERT INTO funds(id,code,name,kind,opening_piasters) VALUES (10,'legacy_bank','Legacy Bank','bank',100000)")
            db.execute("""INSERT INTO vouchers(id,voucher_no,date,kind,from_fund_id,shift,amount_piasters,
                       description,status,created_by,created_at) VALUES
                       (5,'RAM-2026-000005','2026-10-11','receipt',10,'central',50000,
                       'Approved historical synthetic bank posting','approved',1,'2026-10-11')""")
            db.execute("INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on) VALUES (5,10,50000,'2026-10-11')")
        from bootstrap import initialize,connect
        initialize()
        with connect() as db:
            assert db.execute('SELECT opening_piasters FROM funds WHERE id=10').fetchone()[0]==100000
            assert db.execute('SELECT sum(amount_piasters) FROM fund_movements WHERE fund_id=10').fetchone()[0]==50000
            assert db.execute('SELECT status FROM vouchers WHERE id=5').fetchone()[0]=='approved'
            assert db.execute('SELECT count(*) FROM bank_statement_batches').fetchone()[0]==0
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        with connect() as db:
            assert db.execute('SELECT count(*) FROM fund_movements').fetchone()[0]==1
            assert db.execute('SELECT count(*) FROM bank_statement_batches').fetchone()[0]==0
        print('PASS - V7.5 ledger survives additive bank schema upgrade twice without silent matching')
if __name__=='__main__':run()
