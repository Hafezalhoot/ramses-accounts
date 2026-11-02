"""S3: exercise existing financial scripts over a real HTTP socket, not TestClient.

Each suite runs against its own short-lived Uvicorn process and disposable
SQLite, never a hospital DB. No Chromium/TLS or real-device claim is made.
"""
import argparse
import os
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    'cashier_day': 'test_s2_cashier_24h_acceptance.py',
    'deposit_retries': 'test_s2_treasury_retry.py',
    'late_invoice': 'test_v81e_g2b_late_invoice.py',
    'mixed_envelope': 'test_v81e_g2d_mixed_envelope.py',
}


def run_one(suite):
    sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
    os.environ['RAMSES_ENVIRONMENT'] = 'staging'
    os.environ['RAMSES_SECURE_COOKIES'] = '0'  # local loopback only; TLS gate remains open
    for key in ('GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_ID', 'GOOGLE_SHEET_TARGET',
                'RAMSES_LEGACY_FILE'):
        os.environ.pop(key, None)
    from s3_http_transport import RemoteTestClient, transport_info, shutdown_server
    if suite == 'http_security':
        try:
            with tempfile.TemporaryDirectory(prefix='ramses-s3-http-auth-') as tmp:
                os.environ.update(RAMSES_DB_PATH=str(Path(tmp) / 'auth.sqlite3'),
                                  RAMSES_ADMIN_USER='owner',
                                  RAMSES_ADMIN_PASSWORD='s3_local_http_owner_long_password')
                from bootstrap import initialize, connect
                initialize()
                client = RemoteTestClient(None)
                assert client.get('/health').status_code == 200
                homepage = client.get('/')
                assert homepage.status_code == 200 and 'loginForm' in homepage.text
                for asset in ('app.js', 'cashier_ops_ui.js', 'late_entry_ui.js'):
                    assert client.get('/static/' + asset).status_code == 200, asset
                assert client.get('/api/me').status_code == 401
                assert client.post('/api/users', json={'username': 'nope', 'password': 'nope',
                      'role': 'clerk'}).status_code == 401
                login = client.post('/api/login', json={
                    'username': 'owner', 'password': 's3_local_http_owner_long_password'})
                assert login.status_code == 200, login.text
                set_cookie = login.headers.get('set-cookie', '').lower()
                assert 'httponly' in set_cookie and 'samesite=strict' in set_cookie, set_cookie
                token = login.json()['csrf']
                assert client.get('/api/me').status_code == 200
                user = {'username': 's3_reviewer', 'password': 's3_reviewer_secure_long_password',
                        'role': 'reviewer'}
                assert client.post('/api/users', json=user).status_code == 403
                assert client.post('/api/users', json=user,
                                   headers={'X-CSRF-Token': 'bad'}).status_code == 403
                assert client.post('/api/users', json=user,
                                   headers={'X-CSRF-Token': token}).status_code == 200
                other = RemoteTestClient(None)
                other_login = other.post('/api/login', json={
                    'username': user['username'], 'password': user['password']})
                assert other_login.status_code == 200, other_login.text
                other_token = other_login.json()['csrf']
                assert other.post('/api/users', json={
                    'username': 's3_role_forbidden', 'password': 'irrelevant_password',
                    'role': 'clerk'}, headers={'X-CSRF-Token': other_token}).status_code == 403
                forbidden = client.post('/api/users', json={
                    'username': 's3_not_created', 'password': 'irrelevant_password',
                    'role': 'clerk'}, headers={'X-CSRF-Token': other_token})
                assert forbidden.status_code == 403, forbidden.text
                with connect() as c:
                    assert c.execute("SELECT COUNT(*) FROM users WHERE username IN ('s3_not_created','s3_role_forbidden')").fetchone()[0] == 0
                    assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0] == 0
                    assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0] == 0
                print('PASS S3 HTTP security: cookies, independent sessions, 401/403, CSRF and no financial writes', flush=True)
        finally:
            print(transport_info(), flush=True)
            shutdown_server()
        return

    import fastapi.testclient
    from unittest.mock import patch
    try:
        # The genuine existing source acceptance logic runs unchanged.
        with patch.object(fastapi.testclient, 'TestClient', RemoteTestClient):
            runpy.run_path(str(ROOT / 'tests' / SCRIPTS[suite]), run_name='s3_http_suite')['run']()
        assert transport_info()['http_requests'] > 10, 'Not enough real HTTP requests to claim integration'
        print(f'PASS S3 real Uvicorn HTTP: {suite}', flush=True)
    finally:
        print(transport_info(), flush=True)
        shutdown_server()


def main():
    parser = argparse.ArgumentParser(description='Independent real HTTP financial UAT (synthetic only)')
    parser.add_argument('--suite', choices=[*SCRIPTS, 'http_security'])
    args = parser.parse_args()
    if args.suite:
        run_one(args.suite)
        return
    failures = []
    for suite in [*SCRIPTS, 'http_security']:
        print(f'RUN S3 {suite}', flush=True)
        env = os.environ.copy()
        env['RAMSES_ENVIRONMENT'] = 'staging'
        process = subprocess.run([sys.executable, __file__, '--suite', suite], cwd=ROOT,
                                 env=env, text=True, capture_output=True, timeout=120)
        print(process.stdout, end='', flush=True)
        if process.returncode:
            failures.append(suite)
            print(process.stderr[-4000:], file=sys.stderr, flush=True)
    print(f'S3_HTTP_RESULT={len(SCRIPTS)+1-len(failures)}/{len(SCRIPTS)+1} PASS; failures={failures}', flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
