"""G2M offline read-only finance gate catches false-balanced fund journals."""
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts'/'finance_preflight.py'


def run():
    with tempfile.TemporaryDirectory() as d:
        db=Path(d)/'synthetic.sqlite3'
        env={**os.environ,'RAMSES_DB_PATH':str(db),'RAMSES_ADMIN_USER':'qaowner',
             'RAMSES_ADMIN_PASSWORD':'synthetic-test-password-super-long'}
        init=subprocess.run([sys.executable,'-c','from bootstrap import initialize; initialize()'],
                            cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
        assert init.returncode==0,init.stderr
        def check():
            return subprocess.run([sys.executable,str(SCRIPT),'--db',str(db),'--period','2026-08'],
                                  cwd=ROOT,env=env,capture_output=True,text=True,timeout=45)
        first=check()
        assert first.returncode==0,first.stderr
        assert '"status": "PASS"' in first.stdout,first.stdout
        with sqlite3.connect(db) as c:
            account=c.execute('''SELECT account_id FROM gl_fund_accounts fa JOIN funds f ON f.id=fa.fund_id
                                  WHERE f.code='cash_main' ''').fetchone()[0]
            offset=c.execute("SELECT id FROM gl_accounts WHERE code='3100'").fetchone()[0]
            uid=c.execute('SELECT id FROM users WHERE role="owner" LIMIT 1').fetchone()[0]
            c.execute("INSERT INTO gl_journals(entry_date,memo,origin,status,created_by,created_at,reviewed_by,reviewed_at) "
                      "VALUES ('2026-08-08','synthetic unmatched control journal','manual','pending',?,datetime('now'),?,datetime('now'))",
                      (uid,uid))
            jid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.executemany('INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES (?,?,?,?)',
                         ((jid,account,12300,0),(jid,offset,0,12300)))
            c.execute("UPDATE gl_journals SET status='posted' WHERE id=?",(jid,))
            c.commit()
        second=check()
        assert second.returncode==2,second.stdout+second.stderr
        assert '"trial_balance_balanced": true' in second.stdout
        assert '"treasury_reconciliation_ok": false' in second.stdout
        with sqlite3.connect(db) as c:
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==1
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print('PASS G2M read-only accounting preflight catches balanced-but-fake fund journal; no data changed')


if __name__=='__main__':run()
