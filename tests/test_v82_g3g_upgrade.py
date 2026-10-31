"""G3G migration proof: authentic G3F schema -> encrypted pre-DDL rollback -> additive writeoffs.

The G3F schema fixture is byte-frozen from Git commit 0e87a3b, not rewritten
from the new code. Only a synthetic user and inventory item are inserted.
"""
import hashlib
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ORIGINAL=ROOT/'tests/fixtures/schema_v8_1e_g3f_original.sql'
SHA='1342a535b24a005d876791370dc5545a45050b2895992b11b446fc4453505c14'


def run():
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SHA,'Frozen G3F baseline tampered'
    with tempfile.TemporaryDirectory(prefix='ramses-g3g-upgrade-') as temp:
        base=Path(temp); path=base/'g3f-original.sqlite3'
        phrase=base/'backup_passphrase';phrase.write_text('synthetic-standalone-g3g-encryption-key-phrase');phrase.chmod(0o600)
        os.environ.update(RAMSES_DB_PATH=str(path),RAMSES_BACKUP_PASSPHRASE_FILE=str(phrase))
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        with sqlite3.connect(path) as con:
            con.execute('PRAGMA foreign_keys=ON')
            con.executescript(ORIGINAL.read_text(encoding='utf-8'))
            con.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(7,'synthetic-G3F','hash','owner','2026-10-31')")
            con.execute("INSERT INTO inventory_items(id,code,name,unit) VALUES(14,'G3F-OLD-STOCK','Synthetic old item','piece')")
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inventory_return_writeoffs'").fetchone() is None
        from bootstrap import initialize,connect
        initialize()
        with connect() as con:
            assert con.execute("SELECT id FROM users WHERE id=7").fetchone()[0]==7
            assert con.execute("SELECT code FROM inventory_items WHERE id=14").fetchone()[0]=='G3F-OLD-STOCK'
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inventory_return_inspections'").fetchone()
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inventory_return_writeoffs'").fetchone()
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inv_writeoff_approval_guard'").fetchone()
            assert con.execute("SELECT class FROM gl_accounts WHERE code='5195'").fetchone()[0]=='expense'
            assert con.execute('SELECT COUNT(*) FROM inventory_return_writeoffs').fetchone()[0]==0
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert con.execute('PRAGMA foreign_key_check').fetchall()==[]
        backups=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        assert stat.S_IMODE(backups[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'g3f-restored.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as con:
            assert con.execute('SELECT username FROM users WHERE id=7').fetchone()[0]=='synthetic-G3F'
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inventory_return_writeoffs'").fetchone() is None
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert len(list((base/'pre_schema_upgrade_backups').glob('*.rbe')))==1
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3G original G3F frozen migration and encrypted independent rollback; no synthetic writeoff backfill')

if __name__=='__main__':run()
