"""Upgrade V8.0 database to V8.1A without changing historical approved voucher."""
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)
        dbfile=p/'db.sqlite3'
        os.environ['RAMSES_DB_PATH']=str(dbfile)
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='v81_billing_test_password_long'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        # Simulate the old V8.0 schema from its frozen previous package.
        import zipfile
        # Portable fixture: user-provided original ZIP, never a reconstructed schema.
        fixture_name='Ramses_Accounts_V8_0_Double_Entry_Decision_Foundation.zip'
        archive=Path(os.environ.get('RAMSES_V80_ARCHIVE') or ROOT/'tests'/'fixtures'/fixture_name)
        if not archive.is_file():
            legacy=Path('/mnt/data')/fixture_name
            if legacy.is_file():archive=legacy
        if archive.is_file():
            with zipfile.ZipFile(archive) as z:
                target=next(name for name in z.namelist() if name.endswith('/schema.sql'))
                schema=z.read(target).decode()
            with sqlite3.connect(dbfile) as c:
                c.executescript(schema)
                c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,'owner','placeholder','owner','2026-10-30')")
                c.execute("INSERT INTO departments(id,code,name) VALUES (1,'LAB','Test')")
                c.execute("INSERT INTO funds(id,code,name,kind,opening_piasters) VALUES (1,'OLD','Legacy Cash','cash',300)")
                c.execute("INSERT INTO vouchers(id,voucher_no,date,kind,from_fund_id,shift,amount_piasters,description,status,created_by,created_at) VALUES (1,'RAM-OLD','2026-10-01','receipt',1,'central',500,'Original approved movement','approved',1,'2026-10-01')")
                c.execute("INSERT INTO fund_movements(id,voucher_id,fund_id,amount_piasters,booked_on) VALUES (1,1,1,500,'2026-10-01')")
                c.execute("INSERT INTO gl_accounts(id,code,name,class) VALUES (1,'OLD_GL','Legacy','asset')")
                c.execute("INSERT INTO gl_journals(id,entry_date,memo,origin,source_id,status,created_by,created_at) VALUES (1,'2026-10-01','legacy','manual',NULL,'pending',1,'2026-10-01')")
                c.commit()
        else:raise AssertionError(f'Original V8.0 ZIP not found: put it at {ROOT / "tests" / "fixtures" / fixture_name} or set RAMSES_V80_ARCHIVE. Historical migration untested.')
        from bootstrap import initialize,connect
        initialize()
        backup=list((p/'pre_billing_upgrade_backups').glob('*.sqlite3'))
        assert len(backup)==1
        with sqlite3.connect(backup[0]) as c:
            assert c.execute("SELECT count(*) FROM sqlite_master WHERE name='billing_points'").fetchone()[0]==0
            assert c.execute("SELECT amount_piasters FROM vouchers WHERE id=1").fetchone()[0]==500
        with connect() as c:
            assert c.execute("SELECT amount_piasters FROM vouchers WHERE id=1").fetchone()[0]==500
            assert c.execute("SELECT amount_piasters FROM fund_movements WHERE id=1").fetchone()[0]==500
            assert c.execute("SELECT status FROM gl_journals WHERE id=1").fetchone()[0]=='pending'
            assert c.execute("SELECT count(*) FROM billing_points").fetchone()[0]==2
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        initialize()
        assert len(list((p/'pre_billing_upgrade_backups').glob('*.sqlite3')))==1
        print('PASS V8.1A migration from V8.0: voucher/GL intact, consistent pre-upgrade backup, two points, idempotent')

if __name__=='__main__':run()
