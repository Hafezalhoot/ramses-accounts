"""G2J additive schema update must preserve existing V8.1E-G2I data.

Runs original G2I bootstrap against an isolated database and reopens it with
G2J. This is NOT a substitute for the unavailable historical V8.0 archive.
"""
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'ramses_v81i'


def main():
    if not (OLD / 'bootstrap.py').is_file():
        print('SKIP G2J G2I upgrade: original preceding source checkout unavailable')
        return
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'existing_g2i.sqlite3'
        env = {**os.environ, 'RAMSES_DB_PATH': str(path), 'RAMSES_ADMIN_USER':'upgrade_owner',
               'RAMSES_ADMIN_PASSWORD':'test_only_upgrade_password_4567'}
        python = sys.executable
        bootstrap = 'from bootstrap import initialize; initialize()'
        subprocess.run([python,'-c',bootstrap], cwd=OLD, env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with sqlite3.connect(path) as c:
            before = {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                      for t in ('users','funds','gl_accounts','categories','billing_points')}
            old_accounts={r[0]:(r[1],r[2]) for r in c.execute('SELECT code,name,class FROM gl_accounts')}
            old_categories={r[0]:(r[1],r[2]) for r in c.execute('SELECT code,name,direction FROM categories')}
            assert before['users']==1
            assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name='fund_movement_no_update'").fetchone()[0]==0
        subprocess.run([python,'-c',bootstrap], cwd=ROOT, env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        subprocess.run([python,'-c',bootstrap], cwd=ROOT, env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with sqlite3.connect(path) as c:
            after = {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before}
            # G2K introduces one legitimate acquiring-fee account and category.
            # Compare identity and content of every historical row, not just counts.
            assert all(after[t]==before[t] for t in ('users','funds','billing_points')),(before,after)
            assert after['gl_accounts']==before['gl_accounts']+1,(before,after)
            assert after['categories']==before['categories']+1,(before,after)
            assert old_accounts.items() <= {r[0]:(r[1],r[2]) for r in c.execute('SELECT code,name,class FROM gl_accounts')}.items()
            assert old_categories.items() <= {r[0]:(r[1],r[2]) for r in c.execute('SELECT code,name,direction FROM categories')}.items()
            assert c.execute("SELECT class FROM gl_accounts WHERE code='5176'").fetchone()[0]=='expense'
            assert c.execute("SELECT direction FROM categories WHERE code='pos_processing_fee'").fetchone()[0]=='payment'
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            for name in ('fund_movement_no_update','fund_movement_no_delete',
                         'signed_bank_batch_no_update','signed_bank_line_no_delete',
                         'signed_bank_match_no_insert'):
                assert c.execute('SELECT 1 FROM sqlite_master WHERE type="trigger" AND name=?',
                                 (name,)).fetchone(),name
            for name in ('pos_approved_no_update','pos_approved_no_delete',
                         'pos_parts_no_modify','pos_parts_no_delete','pos_parts_no_insert'):
                assert c.execute('SELECT 1 FROM sqlite_master WHERE type="trigger" AND name=?',(name,)).fetchone(),name
        print('PASS G2K migration: G2I rows kept intact, exactly one new fee account/category, POS schema repeat-safe')


if __name__=='__main__':
    main()
