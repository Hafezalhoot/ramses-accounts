"""G3K: authentic frozen G3J schema -> additive linked supplier bank vouchers with encrypted rollback."""
import hashlib
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ORIGINAL=ROOT/'tests/fixtures/schema_v8_1e_g3j_original.sql'
SHA='9754f74a5a316e56cb1919de1f3c7ae8059f0f7ad9d606dad653fa786bd70fc6'


def run():
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SHA,'Frozen signed source of G3J was modified'
    with tempfile.TemporaryDirectory(prefix='ramses-g3k-upgrade-') as tmp:
        base=Path(tmp);dbpath=base/'synthetic-old-g3j.sqlite3'
        phrase=base/'backup_key';phrase.write_text('synthetic-encrypted-g3k-migration-test-passphrase')
        phrase.chmod(0o600)
        os.environ.update(RAMSES_DB_PATH=str(dbpath),RAMSES_BACKUP_PASSPHRASE_FILE=str(phrase))
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        with sqlite3.connect(dbpath) as con:
            con.execute('PRAGMA foreign_keys=ON')
            con.executescript(ORIGINAL.read_text(encoding='utf8'))
            con.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(19,'g3j-original','hash','owner','2026-10-31')")
            con.execute("INSERT INTO inventory_vendors(id,code,name) VALUES(17,'ORIGINAL-G3J','Historical synthetic supplier')")
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inventory_supplier_payment_requests'").fetchone()
            assert not con.execute("SELECT name FROM sqlite_master WHERE name='inventory_supplier_bank_vouchers'").fetchone()
        from bootstrap import initialize,connect
        initialize()
        with connect() as con:
            assert con.execute("SELECT id FROM users WHERE username='g3j-original'").fetchone()[0]==19
            assert con.execute("SELECT code FROM inventory_vendors WHERE id=17").fetchone()[0]=='ORIGINAL-G3J'
            assert con.execute("SELECT name FROM sqlite_master WHERE name='inventory_supplier_bank_vouchers'").fetchone()
            assert con.execute("SELECT name FROM sqlite_master WHERE name='supplier_bank_voucher_approval_guard'").fetchone()
            assert con.execute("SELECT id FROM categories WHERE code='supplier_ap_settlement'").fetchone()
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not con.execute('PRAGMA foreign_key_check').fetchall()
        backups=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        assert stat.S_IMODE(backups[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'restored-original-g3j.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as con:
            assert con.execute("SELECT code FROM inventory_vendors WHERE id=17").fetchone()[0]=='ORIGINAL-G3J'
            assert not con.execute("SELECT name FROM sqlite_master WHERE name='inventory_supplier_bank_vouchers'").fetchone()
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert len(list((base/'pre_schema_upgrade_backups').glob('*.rbe')))==1
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3K frozen Git G3J migration with independently restored encrypted rollback')

if __name__=='__main__':run()
