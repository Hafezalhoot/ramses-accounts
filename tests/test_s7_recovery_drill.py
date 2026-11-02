"""S7: offline transport proof and read-only app smoke from recovered copy.

Synthetic test fixtures only; same test host, NOT a physical second workstation.
"""
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / 'scripts' / 'secure_backup.py'
DRILL = ROOT / 'scripts' / 'recovery_drill.py'


def call(script, env, *args):
    return subprocess.run([sys.executable, str(script), *map(str, args)],
                          env=env, cwd=ROOT, capture_output=True, text=True, timeout=100)


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s7-test-') as rootdir:
        home = Path(rootdir)
        origin, offsite, keydir = (home / x for x in ('origin', 'offsite-copy', 'separate-key'))
        for directory in (origin, offsite, keydir):
            directory.mkdir(mode=0o700)
        db = origin / 'ledger.sqlite3'
        key = keydir / 'private-passphrase'
        key.write_bytes(b'S7-test-strong-private-passphrase-only-2026')
        key.chmod(0o600)
        env = {**os.environ, 'RAMSES_DB_PATH':str(db), 'RAMSES_ADMIN_USER':'s7owner',
               'RAMSES_ADMIN_PASSWORD':'s7_fake_bootstrap_password_very_long',
               'RAMSES_BACKUP_PASSPHRASE_FILE':str(key), 'RAMSES_ENVIRONMENT':'staging'}
        for name in ('GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_ID',
                     'GOOGLE_SHEET_TARGET', 'RAMSES_BACKUP_PASSPHRASE', 'RAMSES_LEGACY_FILE'):
            env.pop(name, None)
        init = subprocess.run([sys.executable, '-c',
               'from bootstrap import initialize; initialize()'], cwd=ROOT, env=env,
               capture_output=True, text=True, timeout=65)
        assert init.returncode == 0, init.stderr[-1200:]
        marker = 'FAKE-S7-TEST-ONLY-MARKER-DO-NOT-EXPOSE'
        with sqlite3.connect(db) as connection:
            connection.execute("INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at) "
                               "VALUES (1,'drill','synthetic','s7',?,CURRENT_TIMESTAMP)", (marker,))
            connection.commit()
        made = call(BACKUP, env, 'create', '--db', db, '--output-dir', origin/'private-backups')
        assert made.returncode == 0, made.stderr[-1800:]
        archive = next((origin/'private-backups').glob('*.rbe'))
        transported = offsite/'copied.rbe'
        transported.write_bytes(archive.read_bytes())
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        before = db.read_bytes()
        output = offsite/'recovery-test'
        command = ('--archive', transported, '--expected-sha256', digest, '--output-dir')
        ok = call(DRILL, env, *command, output)
        assert ok.returncode == 0, ok.stderr[-1400:] + ok.stdout[-800:]
        restored = output/'recovered.sqlite3'
        report_path = output/'recovery_report.json'
        assert restored.is_file() and report_path.is_file()
        assert stat.S_IMODE(restored.stat().st_mode)==0o600
        assert stat.S_IMODE(output.stat().st_mode)==0o700
        assert stat.S_IMODE(report_path.stat().st_mode)==0o600
        report = json.loads(report_path.read_text(encoding='utf8'))
        assert report['status']=='PASS' and report['archive_sha256']==digest
        assert report['app_health_http_status']==200
        assert report['unauthenticated_api_http_status']==401
        assert report['physical_off_device_drill_verified'] is False
        assert report['restored_sha256']==hashlib.sha256(restored.read_bytes()).hexdigest()
        assert report['financial_integrity']=='PASS'
        assert marker not in report_path.read_text() and key.read_text() not in report_path.read_text()
        assert str(db) not in report_path.read_text() and str(transported) not in report_path.read_text()
        with sqlite3.connect(restored) as c:
            assert c.execute('SELECT COUNT(*) FROM audit_log WHERE details=?',(marker,)).fetchone()[0]==1
        assert db.read_bytes()==before, 'Recovery drill must never alter original ledger'
        # A correct digest must be supplied by the source operator, independently.
        wrong_hash = call(DRILL, env, '--archive', transported, '--expected-sha256', '0'*64,
                          '--output-dir', offsite/'wrong-hash')
        assert wrong_hash.returncode!=0 and not (offsite/'wrong-hash').exists()
        # Incorrect passphrase should not leave an unencrypted recovery file.
        bad_key = keydir/'wrong-passphrase'
        bad_key.write_bytes(b'Another-long-wrong-test-passphrase')
        bad_key.chmod(0o600)
        wrong_env = {**env, 'RAMSES_BACKUP_PASSPHRASE_FILE':str(bad_key)}
        wrong_key = call(DRILL, wrong_env, *command, offsite/'wrong-key')
        assert wrong_key.returncode!=0 and not (offsite/'wrong-key').exists()
        tampered = offsite/'tampered.rbe'
        contents = bytearray(transported.read_bytes())
        contents[len(contents)//2] ^= 0x01
        tampered.write_bytes(contents)
        tampered_digest = hashlib.sha256(contents).hexdigest()
        fail = call(DRILL, env, '--archive', tampered, '--expected-sha256', tampered_digest,
                    '--output-dir', offsite/'tampered-result')
        assert fail.returncode!=0 and not (offsite/'tampered-result').exists()
        keep = offsite/'do-not-touch'
        keep.mkdir()
        sentinel = keep/'KEEP.txt'
        sentinel.write_text('unchanged')
        refuse = call(DRILL, env, *command, keep)
        assert refuse.returncode!=0 and sentinel.read_text()=='unchanged'
        alias = offsite/'symlink-to-existing'
        alias.symlink_to(keep, target_is_directory=True)
        alias_refuse = call(DRILL, env, *command, alias)
        assert alias_refuse.returncode!=0 and alias.is_symlink() and sentinel.read_text()=='unchanged'
        missing = call(DRILL, env, '--archive', offsite/'missing.rbe',
                       '--expected-sha256', digest, '--output-dir', offsite/'missing-result')
        assert missing.returncode!=0 and not (offsite/'missing-result').exists()
        assert db.read_bytes()==before
        # A copied archive might be replaced with a DIFFERENT, validly encrypted
        # archive after the transfer hash is checked and before decryption.
        # It must not produce a PASS report associated with the original hash.
        with sqlite3.connect(db) as connection:
            connection.execute("INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at) "
                               "VALUES (1,'drill','synthetic','newer',?,CURRENT_TIMESTAMP)",
                               ('S7-SECOND-DIFFERENT-VALID-ARCHIVE',))
            connection.commit()
        second_folder = origin/'second-private-backup'
        second_made = call(BACKUP, env, 'create', '--db', db, '--output-dir', second_folder)
        assert second_made.returncode==0, second_made.stderr[-1000:]
        second_archive = next(second_folder.glob('*.rbe'))
        transported.write_bytes(archive.read_bytes())
        sys.path.insert(0, str(ROOT/'scripts'))
        import recovery_drill
        from unittest.mock import patch
        raced = offsite/'archive-changed-during-drill'
        real_mkdir = Path.mkdir

        def switch_after_hash(self, *args, **kwargs):
            result = real_mkdir(self, *args, **kwargs)
            if self == raced:
                transported.write_bytes(second_archive.read_bytes())
            return result

        with patch.dict(os.environ, env, clear=True), patch.object(Path, 'mkdir', switch_after_hash):
            try:
                recovery_drill.drill(transported, digest, raced)
            except ValueError as error:
                assert 'changed' in str(error).lower() or 'sha-256' in str(error).lower(), str(error)
            else:
                raise AssertionError('An archive changed after SHA256 preflight must be rejected')
        assert not raced.exists(), 'No recovered sensitive database may survive the archive-swap failure'
        print('PASS S7 recovery drill: hash-bound ciphertext, separate-process app smoke, no-clobber, bad hash/key/tamper, archive swap, PHI-free report')


if __name__=='__main__':
    run()
