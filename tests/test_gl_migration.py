"""Existing V7.8 financial data is preserved and never certified or backfilled silently."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'prior-version.sqlite3'
        os.environ['RAMSES_DB_PATH']=str(path)
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='very_long_test_password_16'
        from bootstrap import initialize,connect,seed,hash_password,now
        c=sqlite3.connect(path)
        c.executescript((ROOT/'tests/fixtures/v7_8_schema.sql').read_text())
        c.row_factory=sqlite3.Row
        with c:
            seed(c)
            uid=c.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)',
                          ('owner',hash_password('very_long_test_password_16'),'owner',now())).lastrowid
            cur=c.execute("""INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,from_fund_id,
                    shift,amount_piasters,description,status,created_by,reviewed_by,created_at,reviewed_at)
                    VALUES (?,?,?,?,? ,?,'central',?,'legacy approved voucher','approved',?,?,?,?)""",
                          ('RAM-2026-000009','2026-09-09','receipt',1,1,1,4900,uid,uid,now(),now()))
            c.execute('INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on) VALUES (?,?,?,?)',
                      (cur.lastrowid,1,4900,'2026-09-09'))
        before=(c.execute('SELECT count(*) FROM vouchers').fetchone()[0],
                c.execute('SELECT sum(amount_piasters) FROM fund_movements').fetchone()[0])
        c.close()
        initialize()  # V8 additive migration
        snapshots=list((path.parent/'pre_gl_upgrade_backups').glob('before_v8_*.sqlite3'))
        assert len(snapshots)==1
        with sqlite3.connect(snapshots[0]) as snap:
            assert snap.execute("SELECT count(*) FROM sqlite_master WHERE name='gl_journals'").fetchone()[0]==0
            assert snap.execute('SELECT count(*) FROM vouchers').fetchone()[0]==before[0]
        assert (snapshots[0].stat().st_mode & 0o777)==0o600
        with connect() as after:
            assert after.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='gl_journals'").fetchone()[0]==1
            assert after.execute('SELECT count(*) FROM vouchers').fetchone()[0]==before[0]
            assert after.execute('SELECT sum(amount_piasters) FROM fund_movements').fetchone()[0]==before[1]
            assert after.execute('SELECT count(*) FROM gl_journals').fetchone()[0]==0
            from ledger import coverage
            result=coverage(after,'2026-09')
            assert result['unposted_vouchers']==1 and result['not_final']
        print('PASS V8 migration - old cash vouchers kept, old postings not silently certified into GL')

if __name__=='__main__':run()
