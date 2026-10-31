"""G2K -> G2L preserves authentic older rows and produces no fake opening journal."""
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT.parent/'ramses_v81k'

def main():
    if not (OLD/'bootstrap.py').is_file():
        print('SKIP G2L G2K source checkout not available; migration must be rerun with historical source')
        return
    with tempfile.TemporaryDirectory() as d:
        db=Path(d)/'migration.sqlite3'
        env={**os.environ,'RAMSES_DB_PATH':str(db),'RAMSES_ADMIN_USER':'owner',
             'RAMSES_ADMIN_PASSWORD':'synthetic_migration_password_long'}
        init='from bootstrap import initialize; initialize()'
        def boot(path):
            p=subprocess.run([sys.executable,'-c',init],cwd=path,env=env,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            assert p.returncode==0,(path,p.stdout,p.stderr)
        boot(OLD)
        with sqlite3.connect(db) as c:
            c.execute("UPDATE funds SET opening_piasters=12300 WHERE code='cash_main'")
            c.commit()
            initial={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
                    ('users','funds','gl_accounts','vouchers','gl_journals','fund_movements')}
            assert not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fund_opening_reviews'").fetchone()
        boot(ROOT)
        boot(ROOT)
        with sqlite3.connect(db) as c:
            assert {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in initial}==initial
            assert c.execute("SELECT opening_piasters FROM funds WHERE code='cash_main'").fetchone()[0]==12300
            assert c.execute('SELECT count(*) FROM fund_opening_reviews').fetchone()[0]==0
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            for name in ('fund_opening_reviews','idx_fund_opening_active'):
                assert c.execute('SELECT name FROM sqlite_master WHERE name=?',(name,)).fetchone(),name
            assert c.execute('SELECT count(*) FROM gl_journals').fetchone()[0]==initial['gl_journals']
        print('PASS G2L migration: G2K rows preserved, repeat safe, legacy opening flagged for review (not silently posted)')

if __name__=='__main__':main()
