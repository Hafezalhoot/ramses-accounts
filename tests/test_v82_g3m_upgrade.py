"""G3M: frozen authentic G3L schema, additive attribution and encrypted rollback restore."""
import hashlib,os,sqlite3,stat,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ORIGINAL=ROOT/'tests/fixtures/schema_v8_1e_g3l_original.sql'
SHA='bf4f12a06960a3de707d76a649296a4382f24687a2ff76bcd17bd5362b341b26'

def run():
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()==SHA,'Frozen authentic G3L schema changed'
    with tempfile.TemporaryDirectory(prefix='ramses-g3m-upgrade-') as tmp:
        base=Path(tmp);dbpath=base/'old-g3l-synthetic.sqlite3';key=base/'backup_key'
        key.write_text('g3m-only-synthetic-archive-encryption-passphrase')
        key.chmod(0o600)
        os.environ.update(RAMSES_DB_PATH=str(dbpath),RAMSES_BACKUP_PASSPHRASE_FILE=str(key))
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        with sqlite3.connect(dbpath) as c:
            c.execute('PRAGMA foreign_keys=ON')
            c.executescript(ORIGINAL.read_text(encoding='utf8'))
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(29,'g3l-archived','hash','owner','2026-10-31')")
            c.execute("INSERT INTO inventory_vendors(id,code,name) VALUES(30,'G3L-ORIGINAL','Synthetic old vendor')")
            assert not c.execute("SELECT name FROM sqlite_master WHERE name='supplier_journal_attributions'").fetchone()
        from bootstrap import initialize,connect
        initialize()
        with connect() as c:
            assert c.execute("SELECT id FROM users WHERE username='g3l-archived'").fetchone()[0]==29
            assert c.execute("SELECT code FROM inventory_vendors WHERE id=30").fetchone()[0]=='G3L-ORIGINAL'
            assert c.execute("SELECT name FROM sqlite_master WHERE name='supplier_journal_attributions'").fetchone()
            assert c.execute("SELECT name FROM sqlite_master WHERE name='supplier_attribution_review_guard'").fetchone()
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        backups=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        assert stat.S_IMODE(backups[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'independent_restored_old_g3l.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as c:
            assert c.execute("SELECT code FROM inventory_vendors WHERE id=30").fetchone()[0]=='G3L-ORIGINAL'
            assert not c.execute("SELECT name FROM sqlite_master WHERE name='supplier_journal_attributions'").fetchone()
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert len(list((base/'pre_schema_upgrade_backups').glob('*.rbe')))==1
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3M frozen authentic G3L schema upgrade / encrypted rollback restore / no fake attribution')
if __name__=='__main__':run()
