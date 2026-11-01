"""G3N upgrades exact frozen G3M schema with encrypted pre-upgrade rollback."""
import hashlib,os,sqlite3,stat,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FROZEN=ROOT/'tests/fixtures/schema_v8_1e_g3m_original.sql'
SHA='957e5c2ad9d19a28f1f7a9c72cf97331048e03d0820f3767a001a9ad743ed65b'

def run():
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest()==SHA,'G3M frozen source schema was modified'
    with tempfile.TemporaryDirectory(prefix='ramses-g3n-upgrade-') as tmp:
        root=Path(tmp);dbpath=root/'g3m_previous_synthetic.sqlite3';key=root/'g3n_backup_key'
        key.write_text('only-a-test-g3n-encrypted-archive-passphrase')
        key.chmod(0o600)
        os.environ.update(RAMSES_DB_PATH=str(dbpath),RAMSES_BACKUP_PASSPHRASE_FILE=str(key))
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        with sqlite3.connect(dbpath) as c:
            c.execute('PRAGMA foreign_keys=ON')
            c.executescript(FROZEN.read_text(encoding='utf8'))
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(37,'g3m-archived','synthetic_hash','owner','2026-10-31')")
            c.execute("INSERT INTO inventory_vendors(id,code,name) VALUES(38,'G3M-FROZEN','Synthetic preceding vendor')")
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='supplier_opening_statements'").fetchone()
        from bootstrap import initialize,connect
        initialize()
        with connect() as c:
            assert c.execute("SELECT id FROM users WHERE username='g3m-archived'").fetchone()[0]==37
            assert c.execute("SELECT code FROM inventory_vendors WHERE id=38").fetchone()[0]=='G3M-FROZEN'
            assert c.execute("SELECT name FROM sqlite_master WHERE name='supplier_opening_statements'").fetchone()
            assert c.execute("SELECT name FROM sqlite_master WHERE name='supplier_opening_review_guard'").fetchone()
            assert c.execute('SELECT COUNT(*) FROM supplier_opening_statements').fetchone()[0]==0
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        copies=list((root/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(copies)==1,copies
        assert stat.S_IMODE(copies[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=root/'verified_previous_synthetic.sqlite3'
        verify_or_restore(copies[0],restored)
        with sqlite3.connect(restored) as c:
            assert c.execute("SELECT code FROM inventory_vendors WHERE id=38").fetchone()[0]=='G3M-FROZEN'
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='supplier_opening_statements'").fetchone()
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert len(list((root/'pre_schema_upgrade_backups').glob('*.rbe')))==1
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3N authentic frozen G3M upgrade, encrypted prior schema rollback and idempotent initialization')

if __name__=='__main__':run()
