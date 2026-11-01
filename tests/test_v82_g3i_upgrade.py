"""G3I frozen Git G3H schema -> additive SQL purchasing with encrypted pre-DDL rollback."""
import hashlib
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ORIGINAL=ROOT/'tests/fixtures/schema_v8_1e_g3h_original.sql'
SHA='cf4d283b299a2563991e4d66829fa688d8e5aa3bab31904e8cf0807fe88ab79a'


def run():
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SHA,'G3H frozen original source altered'
    with tempfile.TemporaryDirectory(prefix='ramses-g3i-upgrade-') as tmp:
        base=Path(tmp);dbpath=base/'original-g3h.sqlite3'
        phrase=base/'backup_key';phrase.write_text('synthetic-independent-g3i-encrypted-upgrade-passphrase');phrase.chmod(0o600)
        os.environ.update(RAMSES_DB_PATH=str(dbpath),RAMSES_BACKUP_PASSPHRASE_FILE=str(phrase))
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        with sqlite3.connect(dbpath) as con:
            con.execute('PRAGMA foreign_keys=ON')
            con.executescript(ORIGINAL.read_text(encoding='utf-8'))
            con.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(17,'synthetic-g3h','hash','owner','2026-10-31')")
            con.execute("INSERT INTO inventory_vendors(id,code,name) VALUES(11,'G3H-ORIGINAL','Synthetic legacy vendor')")
            con.execute("INSERT INTO inventory_items(id,code,name,unit) VALUES(15,'G3H-ITEM','Synthetic historical item','piece')")
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inventory_purchase_orders'").fetchone()
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inventory_supplier_due_schedules'").fetchone() is None
        from bootstrap import initialize,connect
        initialize()
        with connect() as con:
            assert con.execute('SELECT id FROM users WHERE username="synthetic-g3h"').fetchone()[0]==17
            assert con.execute('SELECT code FROM inventory_items WHERE id=15').fetchone()[0]=='G3H-ITEM'
            assert con.execute('SELECT code FROM inventory_vendors WHERE id=11').fetchone()[0]=='G3H-ORIGINAL'
            for obj in ('inventory_supplier_due_schedules','inventory_supplier_due_lines'):
                assert con.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?',(obj,)).fetchone(),obj
                assert con.execute('SELECT count(*) FROM '+obj).fetchone()[0]==0,obj
            assert con.execute('SELECT name FROM sqlite_master WHERE name="inv_due_schedule_initial"').fetchone()
            assert con.execute('SELECT name FROM sqlite_master WHERE name="inv_due_schedule_review_guard"').fetchone()
            assert con.execute('SELECT count(*) FROM gl_journals').fetchone()[0]==0
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert con.execute('PRAGMA foreign_key_check').fetchall()==[]
        backups=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        assert stat.S_IMODE(backups[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'restored-original-g3h.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as con:
            assert con.execute('SELECT code FROM inventory_vendors WHERE id=11').fetchone()[0]=='G3H-ORIGINAL'
            assert con.execute('SELECT name FROM sqlite_master WHERE name="inventory_supplier_due_schedules"').fetchone() is None
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert len(list((base/'pre_schema_upgrade_backups').glob('*.rbe')))==1
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3I authenticated frozen G3H migration and independently restored encrypted rollback')

if __name__=='__main__':run()
