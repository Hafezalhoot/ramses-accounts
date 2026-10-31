"""Minimal secure-staging check, using a temporary database and no real credentials."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as temp:
        os.environ['RAMSES_DB_PATH'] = str(Path(temp) / 'test.sqlite3')
        os.environ['RAMSES_ADMIN_USER'] = 'owner'
        os.environ['RAMSES_ADMIN_PASSWORD'] = 'test_only_very_long_password_2026'
        os.environ['RAMSES_SECURE_COOKIES'] = '1'
        os.environ['RAMSES_ENVIRONMENT'] = 'staging'
        from bootstrap import initialize
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        client = TestClient(app, base_url='https://testserver')
        assert client.get('/health').json()['status'] == 'ok'
        # Readiness must fail if the ledger disappears instead of reporting a false 200.
        db_path = Path(os.environ['RAMSES_DB_PATH'])
        held = db_path.with_suffix('.offline')
        db_path.rename(held)
        try:
            assert client.get('/health').status_code == 503
        finally:
            held.rename(db_path)
        assert client.get('/health').status_code == 200
        assert client.get('/api/vouchers').status_code == 401
        assert client.get('/api/payroll').status_code == 401
        assert client.get('/api/export/vouchers.csv').status_code == 401
        assert client.get('/api/sync-status').status_code == 401
        resp = client.post('/api/login', json={'username': 'owner', 'password': 'test_only_very_long_password_2026'})
        assert resp.status_code == 200, resp.text
        assert resp.json()['environment'] == 'staging'
        assert 'secure' in resp.headers.get('set-cookie', '').lower()
        assert 'httponly' in resp.headers.get('set-cookie', '').lower()
        assert 'max-age=31536000' in resp.headers.get('strict-transport-security', '')
        assert client.get('/api/me').json()['environment'] == 'staging'
        assert client.post('/api/users',json={'username':'testuser','password':'new_password_123456','role':'clerk'}).status_code==403
        print('PASS - staging marked, secure cookie, HSTS, private endpoints and CSRF verified')


if __name__ == '__main__':
    run()
