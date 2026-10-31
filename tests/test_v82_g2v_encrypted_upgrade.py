"""G2V: migration must fail closed without encryption; legacy snapshots must restore."""
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
MARKER='SYNTHETIC_UPGRADE_ENCRYPTED_MARKER_271828'


def _set_secret(tmp):
    secret=Path(tmp)/'backup_secret_test_only.txt'
    secret.write_text('test-only-a-long-secret-for-upgrade-restore-271828')
    secret.chmod(0o600)
    os.environ['RAMSES_BACKUP_PASSPHRASE_FILE']=str(secret)
    os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
    return secret


def _create_old(path, schema):
    with sqlite3.connect(path) as db:
        db.executescript(schema.read_text(encoding='utf8'))
        db.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(1,?,'synthetic-hash','owner','2026-10-31')",(MARKER,))
        db.commit()


def _run_case(label, schema, expected_folder):
    with tempfile.TemporaryDirectory(prefix='g2v-test-') as td:
        tmp=Path(td)
        path=tmp/'test.sqlite3'
        _create_old(path, schema)
        if label=='partial':
            with sqlite3.connect(path) as original:
                original.execute('ALTER TABLE funds DROP COLUMN cash_restricted')
        os.environ.update(RAMSES_DB_PATH=str(path),RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic-strong-password-271828')
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        import bootstrap
        bootstrap.DB=path  # The two synthetic fixtures run in this same process.
        initialize=bootstrap.initialize
        from scripts.secure_backup import MAGIC, verify_or_restore
        try:
            initialize()
        except (ValueError, RuntimeError) as error:
            assert 'passphrase' in str(error).lower(),(label,str(error))
        else:
            raise AssertionError('Migration succeeded without encrypted rollback passphrase: '+label)
        with sqlite3.connect(path) as c:
            assert c.execute('SELECT username FROM users WHERE id=1').fetchone()[0]==MARKER
            if label=='g2t':
                assert 'service_date' not in {r[1] for r in c.execute('PRAGMA table_info(billing_case_lines)')}
            elif label=='v7':
                assert c.execute("SELECT name FROM sqlite_master WHERE name='gl_journals'").fetchone() is None
            else:
                assert 'cash_restricted' not in {r[1] for r in c.execute('PRAGMA table_info(funds)')}
        assert not list(tmp.rglob('*.rbe')), 'No backup should be published if key is unavailable'
        assert not list(tmp.rglob('before_*.sqlite3')), 'No plaintext rollback copy may remain'

        key=_set_secret(tmp)
        key.chmod(0o644)
        try:
            initialize()
        except (ValueError, RuntimeError) as error:
            assert 'permissions' in str(error).lower()
        else:
            raise AssertionError('Migration allowed an insecure key file')
        assert not list(tmp.rglob('*.rbe'))
        key.chmod(0o600)
        initialize()
        backup_dir=tmp/expected_folder
        archives=list(backup_dir.glob('*.rbe'))
        assert len(archives)==1, (label,archives)
        archive=archives[0]
        assert stat.S_IMODE(archive.stat().st_mode)==0o600
        assert stat.S_IMODE(backup_dir.stat().st_mode)==0o700
        assert archive.read_bytes().startswith(MAGIC)
        assert MARKER.encode('utf8') not in archive.read_bytes()
        assert not list(backup_dir.glob('*.sqlite3'))
        if label=='v7':
            assert len(list((tmp/'pre_v81e_shift_backups').glob('*.rbe')))==1
        assert not list(backup_dir.glob('.ramses-*'))
        isolated=tmp/'isolated_recovery_device'
        isolated.mkdir()
        restored=isolated/'restored-old.sqlite3'
        verified=verify_or_restore(archive,restored)
        assert verified['users']==1,(label,verified)
        with sqlite3.connect(restored) as db:
            assert db.execute('SELECT username FROM users WHERE id=1').fetchone()[0]==MARKER
            if label=='g2t':
                assert 'service_date' not in {r[1] for r in db.execute('PRAGMA table_info(billing_case_lines)')}
            elif label=='v7':
                assert db.execute("SELECT name FROM sqlite_master WHERE name='gl_journals'").fetchone() is None
            else:
                assert 'cash_restricted' not in {r[1] for r in db.execute('PRAGMA table_info(funds)')}
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        # No second snapshot is written on normal restart; original archive unchanged.
        ciphertext=archive.read_bytes()
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        initialize()
        assert list(backup_dir.glob('*.rbe'))==[archive]
        assert archive.read_bytes()==ciphertext
        # Wrong passphrase, tampering and overwrite must never create/replace files.
        wrong=tmp/'wrong.txt'
        wrong.write_text('test-only-a-different-long-secret-271828')
        wrong.chmod(0o600)
        os.environ['RAMSES_BACKUP_PASSPHRASE_FILE']=str(wrong)
        bad_out=tmp/'failed-restore.sqlite3'
        try:
            verify_or_restore(archive,bad_out)
        except Exception:
            pass
        else:
            raise AssertionError('Wrong key accepted')
        assert not bad_out.exists()
        os.environ['RAMSES_BACKUP_PASSPHRASE_FILE']=str(tmp/'backup_secret_test_only.txt')
        try:
            verify_or_restore(archive,restored)
        except ValueError:
            pass
        else:
            raise AssertionError('Restore overwritten existing SQLite file')
        assert archive.read_bytes()==ciphertext
        tampered=tmp/'tampered.rbe'
        modified=bytearray(ciphertext)
        modified[len(modified)//2] ^= 1
        tampered.write_bytes(modified)
        try:
            verify_or_restore(tampered,bad_out)
        except Exception:
            pass
        else:
            raise AssertionError('Tampered snapshot accepted')
        assert not bad_out.exists()
        assert not list(tmp.rglob('before_*.sqlite3'))
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)


def run():
    _run_case('v7',ROOT/'tests/fixtures/v7_8_schema.sql','pre_gl_upgrade_backups')
    _run_case('g2t',ROOT/'tests/fixtures/schema_v8_1e_g2t_original.sql','pre_g2u_upgrade_backups')
    _run_case('partial',ROOT/'schema.sql','pre_schema_upgrade_backups')
    print('PASS G2V: legacy + frozen G2T encrypted upgrade, fail-closed key, authenticated restore and no plaintext rollback')


if __name__=='__main__':
    run()
