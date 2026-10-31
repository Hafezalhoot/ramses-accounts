"""G2M restore drill: real encrypted backup, WAL, tampering and wrong key.

No hospital data; starts from a freshly initialized synthetic SQLite ledger.
"""
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts'/'secure_backup.py'
MARKER = 'SYNTHETIC_LEDGER_PRIVATE_MARKER_8765_DO_NOT_EXPOSE'


def run():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        db=root/'test.sqlite3'
        backups=root/'encrypted'
        out=root/'restored.sqlite3'
        phrase=root/'secret.txt'
        phrase.write_text('synthetic-ultra-long-secret-for-tests-only')
        phrase.chmod(0o600)
        env={**os.environ,'RAMSES_DB_PATH':str(db),'RAMSES_ADMIN_USER':'qaowner',
             'RAMSES_ADMIN_PASSWORD':'TEST-only_bootstrap-password_very_long',
             'RAMSES_BACKUP_PASSPHRASE_FILE':str(phrase)}
        def run_cli(*args,env_override=None):
            return subprocess.run([sys.executable,str(SCRIPT),*map(str,args)],
                                  env=env_override or env,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,text=True,timeout=45)
        init=subprocess.run([sys.executable,'-c','from bootstrap import initialize;initialize()'],
                            cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
        assert init.returncode==0, init.stderr
        # WAL + open connection: the backup must see committed rows without
        # copying the .wal file separately, and must exclude uncommitted rows.
        with sqlite3.connect(db) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute("INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at) "
                      "VALUES (1,'test','synthetic','101',?,CURRENT_TIMESTAMP)",(MARKER,))
            c.commit()
            before={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                    for t in ('users','vouchers','fund_movements','gl_journals','audit_log')}
        made=run_cli('create','--db',db,'--output-dir',backups)
        assert made.returncode==0,(made.stdout,made.stderr)
        archives=list(backups.glob('*.rbe'))
        assert len(archives)==1
        arc=archives[0]
        assert stat.S_IMODE(arc.stat().st_mode)==0o600
        assert stat.S_IMODE(backups.stat().st_mode)==0o700
        ciphertext=arc.read_bytes()
        assert MARKER.encode() not in ciphertext
        assert not list(backups.glob('.ramses-backup-*'))
        ok=run_cli('verify','--input',arc)
        assert ok.returncode==0,ok.stderr
        restored=run_cli('restore','--input',arc,'--output-file',out)
        assert restored.returncode==0,restored.stderr
        assert stat.S_IMODE(out.stat().st_mode)==0o600
        with sqlite3.connect(out) as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before}==before
            assert c.execute('SELECT COUNT(*) FROM audit_log WHERE details=?',(MARKER,)).fetchone()[0]==1
        # No overwrite: an existing accounting database must stay byte-identical.
        old=out.read_bytes()
        refuse=run_cli('restore','--input',arc,'--output-file',out)
        assert refuse.returncode!=0 and out.read_bytes()==old
        # Wrong password and corruption both fail authentication and leave no file.
        wrong={**env,'RAMSES_BACKUP_PASSPHRASE_FILE':'' ,
               'RAMSES_BACKUP_PASSPHRASE':'incorrect-but-long-unique-phrase'}
        no=run_cli('verify','--input',arc,env_override=wrong)
        assert no.returncode!=0 and 'FAIL' in no.stderr
        bad=root/'tampered.rbe'
        corrupted=bytearray(ciphertext)
        corrupted[len(corrupted)//2] ^= 0x01
        bad.write_bytes(corrupted)
        fail=run_cli('restore','--input',bad,'--output-file',root/'newdb.sqlite3')
        assert fail.returncode!=0 and not (root/'newdb.sqlite3').exists()
        cut=root/'truncated.rbe'
        cut.write_bytes(ciphertext[:200])
        fail=run_cli('verify','--input',cut)
        assert fail.returncode!=0
        # Unsafe key-file permissions are rejected rather than ignored.
        phrase.chmod(0o644)
        fail=run_cli('verify','--input',arc)
        assert fail.returncode!=0 and 'permissions' in fail.stderr
        print('PASS G2M AES-GCM backup: WAL snapshot, integrity, real restore, no overwrite, wrong key, tamper, truncation, key permissions')


if __name__=='__main__':
    run()
