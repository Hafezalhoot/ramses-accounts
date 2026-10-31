"""G2J -> G2K additive upgrade retains identifiers, accounts and cashbook history.

When the historical G2J checkout is absent, report a skipped historical-upgrade
check. Self-contained fresh/second-run bootstrap is checked separately.
"""
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT.parent/'ramses_v81j'


def main():
    if not (OLD/'bootstrap.py').is_file():
        print('SKIP G2K historical G2J -> G2K upgrade: G2J source checkout not packaged')
        return
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'g2j_previous.sqlite3'
        env={**os.environ,'RAMSES_DB_PATH':str(path),'RAMSES_ADMIN_USER':'g2k_owner',
             'RAMSES_ADMIN_PASSWORD':'test_only_g2k_upgrade_pw_1'}
        cmd=[sys.executable,'-c','from bootstrap import initialize; initialize()']
        subprocess.run(cmd,cwd=OLD,env=env,check=True,capture_output=True)
        with sqlite3.connect(path) as c:
            c.execute("INSERT INTO departments(code,name) VALUES ('G2K_OLD','Retained hospital department')")
            account_before={r[0]:(r[1],r[2],r[3]) for r in c.execute('SELECT code,name,class,control FROM gl_accounts')}
            category_before={r[0]:(r[1],r[2]) for r in c.execute('SELECT code,name,direction FROM categories')}
            before={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                    for t in ('users','funds','gl_accounts','categories','billing_points','departments')}
            assert not c.execute("SELECT name FROM sqlite_master WHERE name='pos_settlements'").fetchone()
        for _ in range(2):
            subprocess.run(cmd,cwd=ROOT,env=env,check=True,capture_output=True)
        with sqlite3.connect(path) as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            after={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before}
            assert all(after[x]==before[x] for x in ('users','funds','billing_points','departments')),(before,after)
            assert after['gl_accounts']==before['gl_accounts']+1,(before,after)
            assert after['categories']==before['categories']+1,(before,after)
            account_after={r[0]:(r[1],r[2],r[3]) for r in c.execute('SELECT code,name,class,control FROM gl_accounts')}
            category_after={r[0]:(r[1],r[2]) for r in c.execute('SELECT code,name,direction FROM categories')}
            assert account_before.items()<=account_after.items()
            assert category_before.items()<=category_after.items()
            assert account_after['5176'][1]=='expense'
            assert category_after['pos_processing_fee'][1]=='payment'
            assert c.execute('SELECT COUNT(*) FROM pos_settlements').fetchone()[0]==0
            assert c.execute('SELECT COUNT(*) FROM pos_settlement_parts').fetchone()[0]==0
            assert c.execute("SELECT id FROM departments WHERE code='G2K_OLD'").fetchone()
        print('PASS G2K: existing G2J accounts, users, departments and funds retained; two upgrades safe')

if __name__=='__main__':main()
