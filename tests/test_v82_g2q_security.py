"""G2Q TDD regressions: synthetic accounts/ledger only; no production data.

Each test proves one previous P1 security gap. Run: python3 tests/test_v82_g2q_security.py
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def setup(root):
    os.environ['RAMSES_DB_PATH'] = str(root / 'ramses.sqlite3')
    os.environ['RAMSES_ADMIN_USER'] = 'owner'
    os.environ['RAMSES_ADMIN_PASSWORD'] = 'synthetic_owner_secret_2026_testing'
    os.environ.pop('GOOGLE_SHEET_ID', None)
    os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON', None)
    from bootstrap import initialize
    initialize()
    from app import app
    from fastapi.testclient import TestClient
    return app, TestClient


def test_source_scoped_login(app, TestClient):
    attacker = TestClient(app, client=('198.51.100.1', 54545))
    actual_owner = TestClient(app, client=('198.51.100.2', 54546))
    payload = {'username': 'owner', 'password': 'wrong_synthetic_password'}
    for i in range(5):
        r = attacker.post('/api/login', json=payload)
        assert r.status_code == 401, (i, r.status_code, r.text)
    assert attacker.post('/api/login', json=payload).status_code == 429
    # An outsider must not be able to lock the real owner out remotely just by naming them.
    good = actual_owner.post('/api/login', json={'username': 'owner', 'password': 'synthetic_owner_secret_2026_testing'})
    assert good.status_code == 200, (good.status_code, good.text)
    # Even with the *correct* password, attacker's blocked source must not bypass throttling.
    assert attacker.post('/api/login', json={'username': 'owner', 'password': 'synthetic_owner_secret_2026_testing'}).status_code == 429
    flood = TestClient(app, client=('198.51.100.3', 54547))
    for n in range(40):
        r = flood.post('/api/login', json={'username': f'missing_user_{n}', 'password': 'synthetic_no_user'})
        assert r.status_code == 401, (n, r.status_code, r.text)
    assert flood.post('/api/login', json={'username': 'missing_user_41', 'password': 'synthetic_no_user'}).status_code == 429
    assert actual_owner.get('/api/me').status_code == 200


def test_employee_lookup_minimization(app, TestClient):
    owner = TestClient(app)
    resp = owner.post('/api/login', json={'username': 'owner', 'password': 'synthetic_owner_secret_2026_testing'})
    assert resp.status_code == 200, resp.text
    headers = {'X-CSRF-Token': resp.json()['csrf']}
    created = owner.post('/api/employees', headers=headers, json={'name': 'موظف صناعي للاختبار', 'code': 'QA_G2Q_EMP'})
    assert created.status_code == 200, created.text
    for role in ('clerk', 'viewer', 'reviewer'):
        r = owner.post('/api/users', headers=headers, json={'username': f'user_{role}', 'role': role, 'password': 'synthetic_staff_secret_2026'})
        assert r.status_code == 200, (role, r.text)
        c = TestClient(app)
        login = c.post('/api/login', json={'username': f'user_{role}', 'password': 'synthetic_staff_secret_2026'})
        assert login.status_code == 200, login.text
        lookup = c.get('/api/lookups')
        assert lookup.status_code == 200
        staff = lookup.json()['employees']
        if role == 'reviewer':
            assert any(e['code'] == 'QA_G2Q_EMP' for e in staff), staff
        else:
            assert staff == [], (role, staff)
    assert any(e['code'] == 'QA_G2Q_EMP' for e in owner.get('/api/lookups').json()['employees'])


def test_audit_records_immutable(root):
    from bootstrap import connect, initialize
    with connect() as c:
        c.execute("INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at) "
                  "VALUES (1,'synthetic','qa','100','{}',CURRENT_TIMESTAMP)")
        row = c.execute("SELECT id FROM audit_log WHERE entity='qa'").fetchone()
        assert row
        for sql in ("UPDATE audit_log SET details='changed' WHERE id=?", "DELETE FROM audit_log WHERE id=?"):
            try:
                c.execute(sql, (row['id'],))
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError('SQL must not modify the audit trail: ' + sql)
        assert c.execute("SELECT details FROM audit_log WHERE id=?", (row['id'],)).fetchone()[0] == '{}'
    # Reinitialize pre-existing DB safely with no audit row loss.
    initialize()
    with connect() as c:
        assert c.execute("SELECT COUNT(*) FROM audit_log WHERE entity='qa'").fetchone()[0] == 1


def test_plaintext_backup_entrypoint_prohibited(root):
    secret = root / 'backup-key'
    secret.write_text('synthetic-long-backup-secret-2026')
    secret.chmod(0o600)
    target = root / 'encrypted'
    env = {**os.environ, 'RAMSES_BACKUP_PASSPHRASE_FILE': str(secret)}
    result = subprocess.run([sys.executable, str(ROOT / 'backup.py'), '--output-dir', str(target)],
                            cwd=ROOT, env=env, text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, (result.stdout, result.stderr)
    archives = list(target.glob('*.rbe'))
    assert len(archives) == 1, (list(target.iterdir()), result.stdout)
    assert not list(target.glob('*.sqlite*'))
    assert (secret.read_text() != '')
    verified = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'secure_backup.py'),
                               'verify', '--input', str(archives[0])], cwd=ROOT, env=env,
                              text=True, capture_output=True, timeout=45)
    assert verified.returncode == 0, (verified.stdout, verified.stderr)
    bad_env = {**env, 'RAMSES_BACKUP_PASSPHRASE_FILE': ''}
    bad_env.pop('RAMSES_BACKUP_PASSPHRASE', None)
    empty = root / 'no-key'
    denied = subprocess.run([sys.executable, str(ROOT / 'backup.py'), '--output-dir', str(empty)],
                            cwd=ROOT, env=bad_env, stdin=subprocess.DEVNULL,
                            text=True, capture_output=True, timeout=45)
    assert denied.returncode != 0
    assert not list(empty.glob('*.sqlite*')) if empty.is_dir() else True
    local_script = (ROOT / 'scripts' / 'backup_local.sh').read_text()
    assert 'backup_encrypted_docker.sh' in local_script
    assert 'python backup.py' not in local_script


def run():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        app, TestClient = setup(root)
        tests = [lambda: test_source_scoped_login(app, TestClient),
                 lambda: test_employee_lookup_minimization(app, TestClient),
                 lambda: test_audit_records_immutable(root),
                 lambda: test_plaintext_backup_entrypoint_prohibited(root)]
        for test in tests:
            test()
        print('PASS G2Q security: source-scoped throttle, employee minimum disclosure, immutable audit, encrypted-only backup')


if __name__ == '__main__':
    run()
