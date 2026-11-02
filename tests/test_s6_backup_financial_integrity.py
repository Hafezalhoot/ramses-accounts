"""S6 recovery acceptance: off-directory encrypted restore and logical invariants.

All data synthetic. No real hospital identity, remote storage or live DB changes.
Run: python tests/test_s6_backup_financial_integrity.py
"""
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import secure_backup


TABLES = ('users', 'vouchers', 'fund_movements', 'gl_journals', 'gl_lines',
          'audit_log', 'voucher_attachments', 'cashier_shift_attachments',
          'bank_statement_batches', 'periods')


def fingerprint(path):
    """Compare actual rows, including evidence bytes, not just row counts."""
    result = {}
    with sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True) as db:
        for table in TABLES:
            digest = hashlib.sha256()
            rows = db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            for row in rows:
                for value in row:
                    payload = value if isinstance(value, bytes) else repr(value).encode('utf8')
                    digest.update(len(payload).to_bytes(8, 'big'))
                    digest.update(payload)
            result[table] = (db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0], digest.hexdigest())
    return result


def run_cli(env, *args):
    return subprocess.run([sys.executable, str(ROOT/'scripts'/'secure_backup.py'),
                           *map(str, args)], env=env, cwd=ROOT,
                          capture_output=True, text=True, timeout=90)


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s6-recovery-') as temp:
        home = Path(temp)
        primary = home / 'source-device'
        secondary = home / 'isolated-recovery'
        primary.mkdir(mode=0o700)
        secondary.mkdir(mode=0o700)
        db = primary / 'ramses.sqlite3'
        key_a = primary / 'backup-passphrase'
        key_a.write_bytes(b'S6_synthetic_recovery_key_only_2026')
        key_a.chmod(0o600)
        env = {**os.environ, 'RAMSES_DB_PATH': str(db),
               'RAMSES_ADMIN_USER': 'qaowner',
               'RAMSES_ADMIN_PASSWORD': 'synthetic_long_owner_key_for_s6',
               'RAMSES_BACKUP_PASSPHRASE_FILE': str(key_a),
               'RAMSES_ENVIRONMENT': 'staging'}
        for key in ('GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_ID', 'GOOGLE_SHEET_TARGET',
                    'RAMSES_BACKUP_PASSPHRASE'):
            env.pop(key, None)
        # Run initialization in a fresh process, so its cached DB path is correct.
        start = subprocess.run([sys.executable, '-c', 'from bootstrap import initialize;initialize()'],
                               cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        assert start.returncode == 0, start.stderr[-700:]
        with sqlite3.connect(db) as c:
            c.execute('PRAGMA foreign_keys=ON')
            owner = c.execute("SELECT id FROM users WHERE username='qaowner'").fetchone()[0]
            fund = c.execute("SELECT id FROM funds WHERE code='cash_main'").fetchone()[0]
            bank = c.execute("SELECT id FROM funds WHERE code='bank'").fetchone()[0]
            acct_a = c.execute("SELECT id FROM gl_accounts WHERE code='1100'").fetchone()[0]
            acct_b = c.execute("SELECT id FROM gl_accounts WHERE code='4190'").fetchone()[0]
            c.execute('''INSERT INTO gl_journals(entry_date,memo,origin,status,created_by,created_at)
                         VALUES ('2026-10-01','S6 synthetic recovery','manual','pending',?,'2026-10-01')''', (owner,))
            journal = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.executemany('''INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters)
                             VALUES (?,?,?,?)''', [(journal, acct_a, 12000, 0), (journal, acct_b, 0, 12000)])
            c.execute("UPDATE gl_journals SET status='posted' WHERE id=?", (journal,))
            c.execute('''INSERT INTO vouchers(voucher_no,date,kind,from_fund_id,shift,
                         amount_piasters,description,created_by,created_at)
                         VALUES ('S6-TEST','2026-10-01','receipt',?,'morning',10000,
                         'Synthetic voucher: never real',?, '2026-10-01')''', (fund, owner))
            voucher = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            evidence = b'S6-TEST-ONLY-FAKE-PDF-EVIDENCE'
            c.execute('''INSERT INTO voucher_attachments
                         (voucher_id,file_name,media_type,file_size,sha256,content,uploaded_by,created_at)
                         VALUES (?, 'synthetic.pdf','application/pdf',?,?,?,?, '2026-10-01')''',
                      (voucher, len(evidence), hashlib.sha256(evidence).hexdigest(), evidence, owner))
            attachment = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('''INSERT INTO shift_sessions
                         (business_date,shift,fund_id,responsible_id,opened_at,opening_piasters)
                         VALUES ('2026-10-01','morning',?,?,'2026-10-01T08:00:00Z',0)''', (fund,owner))
            shift = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('''INSERT INTO cashier_shift_attachments
                         (shift_session_id,kind,file_name,media_type,file_size,sha256,content,uploaded_by,created_at)
                         VALUES (?, 'report','fake.png','image/png',?,?,?,?, '2026-10-01')''',
                      (shift,len(evidence),hashlib.sha256(evidence).hexdigest(),evidence,owner))
            shift_attachment = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            bank_csv = b'date,amount,description\n2026-10-01,0,Synthetic test only\n'
            c.execute('''INSERT INTO bank_statement_batches
                         (fund_id,period,file_name,sha256,raw_csv,opening_piasters,
                          closing_piasters,imported_by,imported_at)
                         VALUES (?, '2026-10','test.csv',?,?,0,0,?,'2026-10-01')''',
                      (bank,hashlib.sha256(bank_csv).hexdigest(),bank_csv,owner))
            batch = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('''INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at)
                         VALUES (?, 'synthetic','recovery','s6','{}','2026-10-01')''', (owner,))
            c.commit()
        assert secure_backup._verify_sqlite(db)['gl_journals'] == 1
        before = fingerprint(db)

        # Test corruption a privileged DB operator could introduce while
        # integrity_check and foreign_key_check still return clean results.
        with sqlite3.connect(db) as c:
            c.execute('DROP TRIGGER gl_no_posted_line_update')
            c.execute('UPDATE gl_lines SET credit_piasters=11999 WHERE journal_id=? AND credit_piasters>0', (journal,))
        assert _sqlite_checks_green(db)
        must_reject(db, 'journal')
        rejected_dir = primary / 'rejected-backups'
        rejected = run_cli(env, 'create', '--db', db, '--output-dir', rejected_dir)
        assert rejected.returncode != 0 and not list(rejected_dir.glob('*.rbe'))
        # Deliberately simulate a legacy encrypted archive produced before S6:
        # valid AES-GCM is not sufficient when the underlying GL is malformed.
        old_archive = primary / 'synthetic-legacy-corrupt.rbe'
        snapshot = primary / 'corrupt-copy.sqlite3'
        with sqlite3.connect(db) as source, sqlite3.connect(snapshot) as copy:
            source.backup(copy)
        source.close()
        copy.close()
        secure_backup._write_encrypted(snapshot, old_archive, key_a.read_bytes())
        denied = run_cli(env, 'verify', '--input', old_archive)
        assert denied.returncode != 0 and 'journal' in denied.stderr
        no_restore = primary / 'should-not-appear.sqlite3'
        denied = run_cli(env, 'restore', '--input', old_archive, '--output-file', no_restore)
        assert denied.returncode != 0 and not no_restore.exists()
        snapshot.unlink()
        old_archive.unlink()
        with sqlite3.connect(db) as c:
            c.execute('UPDATE gl_lines SET credit_piasters=12000 WHERE journal_id=? AND credit_piasters>0', (journal,))
        must_reject(db, 'trigger')  # a valid balance is unsafe without immutable lines
        with sqlite3.connect(db) as c:
            c.executescript('''CREATE TRIGGER gl_no_posted_line_update BEFORE UPDATE ON gl_lines
                WHEN (SELECT status FROM gl_journals WHERE id=OLD.journal_id)!='pending'
                BEGIN SELECT RAISE(ABORT,'Journal lines are frozen'); END;''')
        assert secure_backup._verify_sqlite(db)['gl_journals'] == 1

        for table, row_id, field, expect in (
            ('voucher_attachments', attachment, 'content', 'voucher_attachments'),
            ('cashier_shift_attachments', shift_attachment, 'content', 'cashier_shift_attachments'),
            ('bank_statement_batches', batch, 'raw_csv', 'bank_statement_batches'),
        ):
            with sqlite3.connect(db) as c:
                original = c.execute(f'SELECT {field} FROM {table} WHERE id=?',(row_id,)).fetchone()[0]
                if table == 'cashier_shift_attachments':
                    c.execute('DROP TRIGGER cashier_shift_attachment_no_update')
                corrupt = bytes([original[0] ^ 0x01]) + original[1:]
                c.execute(f'UPDATE {table} SET {field}=? WHERE id=?', (corrupt,row_id))
            assert _sqlite_checks_green(db)
            must_reject(db, expect)
            with sqlite3.connect(db) as c:
                c.execute(f'UPDATE {table} SET {field}=? WHERE id=?', (original,row_id))
            if table == 'cashier_shift_attachments':
                must_reject(db, 'trigger')
                with sqlite3.connect(db) as c:
                    c.executescript('''CREATE TRIGGER cashier_shift_attachment_no_update
                        BEFORE UPDATE ON cashier_shift_attachments
                        BEGIN SELECT RAISE(ABORT,'Shift evidence is immutable'); END;''')
            assert secure_backup._verify_sqlite(db)['gl_journals'] == 1

        with sqlite3.connect(db) as c:
            c.execute('UPDATE voucher_attachments SET file_size=file_size-1 WHERE id=?',(attachment,))
        must_reject(db, 'voucher_attachments')
        with sqlite3.connect(db) as c:
            c.execute('UPDATE voucher_attachments SET file_size=file_size+1 WHERE id=?',(attachment,))
        assert fingerprint(db) == before
        backups = primary / 'private-archive'
        made = run_cli(env, 'create', '--db', db, '--output-dir', backups)
        assert made.returncode == 0, made.stderr[-1000:]
        archives = list(backups.glob('*.rbe'))
        assert len(archives) == 1
        archive = archives[0]
        assert b'S6-TEST-ONLY-FAKE-PDF-EVIDENCE' not in archive.read_bytes()

        # Simulate separate-device handling: copy only authenticated ciphertext
        # and owner-only key, then restore using a NEW PYTHON PROCESS.
        copied = secondary / 'transported.rbe'
        shutil.copyfile(archive, copied)
        # A separate recovery key store; never colocate actual production
        # recovery keys with off-device encrypted archives.
        recovery_keys = home / 'separate-recovery-key-store'
        recovery_keys.mkdir(mode=0o700)
        key_b = recovery_keys / 'backup-passphrase'
        shutil.copyfile(key_a, key_b)
        key_b.chmod(0o600)
        second_env = {**env, 'RAMSES_BACKUP_PASSPHRASE_FILE':str(key_b)}
        restored = secondary / 'restored.sqlite3'
        replay = run_cli(second_env, 'restore', '--input', copied, '--output-file', restored)
        assert replay.returncode == 0, replay.stderr[-1000:]
        assert restored.stat().st_mode & 0o777 == 0o600
        assert fingerprint(restored) == before
        assert secure_backup._verify_sqlite(restored)['gl_journals'] == 1
        refuse = run_cli(second_env, 'restore', '--input', copied, '--output-file', restored)
        assert refuse.returncode != 0
        assert fingerprint(restored) == before
        # Boot from the restored database via a third process (no source DB path).
        app_env = {**second_env, 'RAMSES_DB_PATH':str(restored), 'PYTHONPATH':str(ROOT)}
        smoke = subprocess.run([sys.executable, '-c',
                "from bootstrap import connect; from app import app; "
                "from fastapi.testclient import TestClient; "
                "c=TestClient(app); r=c.post('/api/login',json={'username':'qaowner',"
                "'password':'synthetic_long_owner_key_for_s6'}); "
                "assert r.status_code==200,(r.status_code,r.text[:250]); "
                "assert c.get('/api/lookups').status_code==200"],
                cwd=secondary, env=app_env, capture_output=True, text=True, timeout=45)
        assert smoke.returncode == 0, smoke.stderr[-1200:]
        print('PASS S6: posts/evidence/bank integrity checks, encrypted copied archive, fresh-process isolated restore, full row fingerprints, app login, no overwrite')


def _sqlite_checks_green(path):
    with sqlite3.connect(path) as c:
        return (c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                and c.execute('PRAGMA foreign_key_check').fetchone() is None)


def must_reject(path, fragment):
    try:
        secure_backup._verify_sqlite(path)
    except ValueError as error:
        assert fragment in str(error), (fragment, str(error))
    else:
        raise AssertionError('Expected restore preflight to reject '+fragment)


if __name__ == '__main__':
    run()
