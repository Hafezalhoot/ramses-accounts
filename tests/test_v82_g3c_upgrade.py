"""Original frozen G3B schema must be backed up before G3C SQL FIFO triggers are added."""
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='g3c-frozen-g3b-') as folder:
        base=Path(folder)
        db=base/'historical-g3b.sqlite3'
        with sqlite3.connect(db) as c:
            c.execute('PRAGMA foreign_keys=ON')
            c.executescript((ROOT/'tests/fixtures/schema_v8_1e_g3b_original.sql').read_text())
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(1,'synthetic-owner','x','owner','2026-10-31')")
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(2,'synthetic-clinician','x','clinician','2026-10-31')")
            c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES('synthetic-g3b-session',2,'synthetic-g3b-csrf','2027-01-01')")
            c.execute("INSERT INTO inventory_vendors(id,code,name) VALUES(11,'G3B-VENDOR','Synthetic historical inventory vendor')")
            c.execute("INSERT INTO inventory_items(id,code,name,unit) VALUES(12,'G3B-ITEM','Synthetic old stock item','piece')")
            c.execute("INSERT INTO inventory_receipts(id,vendor_id,received_on,invoice_ref,evidence_ref,created_by,created_at) VALUES(13,11,'2026-10-30','G3B-HISTORICAL-INVOICE','SYNTH-G3B-GRN-REFERENCE',1,'2026-10-30')")
            c.execute("INSERT INTO inventory_receipt_lines(id,receipt_id,item_id,quantity,unit_cost_piasters) VALUES(14,13,12,5,1200)")
            c.commit()
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='inv_issue_fifo_date_guard'").fetchone()
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        os.environ.update(RAMSES_DB_PATH=str(db),RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g3c_owner_password')
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        from bootstrap import initialize,connect
        try:initialize()
        except (ValueError,RuntimeError) as err:
            assert 'passphrase' in str(err).lower(),str(err)
        else:raise AssertionError('G3B schema mutated by G3C without encrypted pre-DDL backup')
        with sqlite3.connect(db) as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='inv_issue_fifo_date_guard'").fetchone()
            assert c.execute('SELECT quantity FROM inventory_receipt_lines WHERE id=14').fetchone()[0]==5
        password=base/'g3c-rollback.secret'
        password.write_text('synthetic-preupgrade-rollback-g3c-2026-secret-for-test')
        password.chmod(0o600)
        os.environ['RAMSES_BACKUP_PASSPHRASE_FILE']=str(password)
        initialize()
        with connect() as c:
            for name in ('inv_receipt_fifo_date_guard','inv_issue_fifo_date_guard'):
                assert c.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('trigger',name)).fetchone()
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            assert c.execute('SELECT quantity FROM inventory_receipt_lines WHERE id=14').fetchone()[0]==5
            assert c.execute('SELECT role FROM users WHERE id=2').fetchone()[0]=='clinician'
            assert c.execute("SELECT user_id FROM sessions WHERE token_hash='synthetic-g3b-session'").fetchone()[0]==2
        archives=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(archives)==1,archives
        assert stat.S_IMODE(archives[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'isolated-original-g3b.sqlite3'
        verify_or_restore(archives[0],restored)
        with sqlite3.connect(restored) as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='inv_issue_fifo_date_guard'").fetchone()
            assert c.execute('SELECT quantity FROM inventory_receipt_lines WHERE id=14').fetchone()[0]==5
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        initialize()
        assert len(list((base/'pre_schema_upgrade_backups').glob('*.rbe')))==1
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3C frozen G3B encrypted pre-DDL rollback, isolated restore, schema guards, no extra archive')


if __name__=='__main__':run()
