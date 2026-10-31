"""G3D: frozen genuine G3C schema -> authenticated rollback before DDL, restore and no duplicates."""
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3d-frozen-g3c-') as folder:
        base=Path(folder)
        db=base/'real-g3c-history.sqlite3'
        with sqlite3.connect(db) as c:
            c.execute('PRAGMA foreign_keys=ON')
            c.executescript((ROOT/'tests/fixtures/schema_v8_1e_g3c_original.sql').read_text())
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(1,'synthetic-owner','x','owner','2026-10-31')")
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(2,'synthetic-reviewer','x','reviewer','2026-10-31')")
            c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES('g3c-synth-session',2,'g3c-synth-csrf','2027-12-01')")
            c.execute("INSERT INTO inventory_vendors(id,code,name) VALUES(17,'G3C_VENDOR','Synthetic frozen G3C supplier')")
            c.execute("INSERT INTO inventory_items(id,code,name,unit) VALUES(18,'G3C_ITEM','Synthetic frozen G3C consumable','piece')")
            c.execute("INSERT INTO inventory_receipts(id,vendor_id,received_on,invoice_ref,evidence_ref,created_by,created_at) VALUES(19,17,'2026-10-30','G3C-SYNTH-INV-1','G3C-SYNTHETIC-GRN',1,'2026-10-30')")
            c.execute("INSERT INTO inventory_receipt_lines(id,receipt_id,item_id,quantity,unit_cost_piasters) VALUES(20,19,18,8,1250)")
            c.commit()
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_issue_returns'").fetchone()
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        os.environ.update(RAMSES_DB_PATH=str(db),RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g3d_owner_pw')
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        from bootstrap import initialize,connect
        try:
            initialize()
        except (RuntimeError,ValueError) as exc:
            assert 'passphrase' in str(exc).lower(),str(exc)
        else:
            raise AssertionError('Existing G3C was silently changed without encrypted backup secret')
        with sqlite3.connect(db) as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_issue_returns'").fetchone()
            assert c.execute('SELECT quantity FROM inventory_receipt_lines WHERE id=20').fetchone()[0]==8
        secret=base/'g3d-rollback-key.secret'
        secret.write_text('synthetic-g3d-backup-passphrase-for-test-only')
        secret.chmod(0o600)
        os.environ['RAMSES_BACKUP_PASSPHRASE_FILE']=str(secret)
        initialize()
        with connect() as c:
            for name in ('inventory_issue_returns','inventory_return_lines'):
                assert c.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',name)).fetchone()
            for name in ('inv_return_approval_guard','inv_return_line_valid','inv_return_no_delete'):
                assert c.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('trigger',name)).fetchone()
            current=c.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='inv_issue_allocation_guard'").fetchone()['sql']
            assert 'inventory_issue_returns' in current,current
            assert c.execute('SELECT quantity FROM inventory_receipt_lines WHERE id=20').fetchone()[0]==8
            assert c.execute('SELECT user_id FROM sessions WHERE token_hash=?',('g3c-synth-session',)).fetchone()[0]==2
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        backups=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        assert stat.S_IMODE(backups[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'g3c-original-restored.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_issue_returns'").fetchone()
            assert c.execute('SELECT quantity FROM inventory_receipt_lines WHERE id=20').fetchone()[0]==8
            assert 'inventory_issue_returns' not in c.execute("SELECT sql FROM sqlite_master WHERE name='inv_issue_allocation_guard'").fetchone()[0]
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        initialize()
        assert len(list((base/'pre_schema_upgrade_backups').glob('*.rbe')))==1
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3D original G3C encrypted pre-DDL snapshot, one-time FIFO trigger replacement, isolated recovery and preserved history')


if __name__=='__main__':
    run()
