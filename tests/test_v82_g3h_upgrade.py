"""G3H frozen Git G3G schema -> additive SQL purchasing with encrypted pre-DDL rollback."""
import hashlib
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ORIGINAL=ROOT/'tests/fixtures/schema_v8_1e_g3g_original.sql'
SHA='3716cbad68856b98a5a2c15611a3ef8078f5b6f55ca6815b61eb96b76cbaafaf'


def run():
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SHA,'G3G frozen original source altered'
    with tempfile.TemporaryDirectory(prefix='ramses-g3h-upgrade-') as tmp:
        base=Path(tmp);dbpath=base/'original-g3g.sqlite3'
        phrase=base/'backup_key';phrase.write_text('synthetic-independent-g3h-encrypted-upgrade-passphrase');phrase.chmod(0o600)
        os.environ.update(RAMSES_DB_PATH=str(dbpath),RAMSES_BACKUP_PASSPHRASE_FILE=str(phrase))
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        with sqlite3.connect(dbpath) as con:
            con.execute('PRAGMA foreign_keys=ON')
            con.executescript(ORIGINAL.read_text(encoding='utf-8'))
            con.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(17,'synthetic-g3g','hash','owner','2026-10-31')")
            con.execute("INSERT INTO inventory_vendors(id,code,name) VALUES(11,'G3G-ORIGINAL','Synthetic legacy vendor')")
            con.execute("INSERT INTO inventory_items(id,code,name,unit) VALUES(15,'G3G-ITEM','Synthetic historical item','piece')")
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inventory_purchase_orders'").fetchone() is None
        from bootstrap import initialize,connect
        initialize()
        with connect() as con:
            assert con.execute('SELECT id FROM users WHERE username="synthetic-g3g"').fetchone()[0]==17
            assert con.execute('SELECT code FROM inventory_items WHERE id=15').fetchone()[0]=='G3G-ITEM'
            assert con.execute('SELECT code FROM inventory_vendors WHERE id=11').fetchone()[0]=='G3G-ORIGINAL'
            for obj in ('inventory_purchase_orders','inventory_purchase_order_lines',
                        'inventory_receipt_purchase_links','inventory_supplier_invoice_matches'):
                assert con.execute('SELECT name FROM sqlite_master WHERE type="table" AND name=?',(obj,)).fetchone(),obj
                assert con.execute('SELECT count(*) FROM '+obj).fetchone()[0]==0,obj
            assert con.execute('SELECT name FROM sqlite_master WHERE name="inv_po_receipt_link_guard"').fetchone()
            assert con.execute('SELECT name FROM sqlite_master WHERE name="inv_supplier_invoice_approval"').fetchone()
            assert con.execute('SELECT count(*) FROM gl_journals').fetchone()[0]==0
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert con.execute('PRAGMA foreign_key_check').fetchall()==[]
        backups=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        assert stat.S_IMODE(backups[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'restored-original-g3g.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as con:
            assert con.execute('SELECT code FROM inventory_vendors WHERE id=11').fetchone()[0]=='G3G-ORIGINAL'
            assert con.execute('SELECT name FROM sqlite_master WHERE name="inventory_purchase_orders"').fetchone() is None
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert len(list((base/'pre_schema_upgrade_backups').glob('*.rbe')))==1
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3H authenticated frozen G3G migration and independently restored encrypted rollback')

if __name__=='__main__':run()
