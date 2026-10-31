"""G2W: unscoped viewer cannot inspect full-hospital journal details. Synthetic only."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td) / 'g2w.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g2w_secure_owner_password')
        from bootstrap import initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner, viewer = TestClient(app), TestClient(app)
        login = owner.post('/api/login', json={'username':'owner','password':'synthetic_g2w_secure_owner_password'})
        assert login.status_code == 200, login.text
        headers = {'X-CSRF-Token':login.json()['csrf']}
        created = owner.post('/api/users', headers=headers, json={
            'username':'viewer_g2w','role':'viewer','password':'synthetic_g2w_secure_viewer_password'})
        assert created.status_code == 200, created.text
        assert viewer.post('/api/login', json={'username':'viewer_g2w','password':'synthetic_g2w_secure_viewer_password'}).status_code == 200
        for path in ('/api/accounting/trial-balance?period=2026-10',
                     '/api/accounting/trial-balance.csv?period=2026-10',
                     '/api/accounting/journals?period=2026-10'):
            r = viewer.get(path)
            assert r.status_code == 403, (path, r.status_code, r.text[:150])
            assert owner.get(path).status_code == 200, path
        print('PASS G2W global ledger viewer scope')

if __name__ == '__main__':
    run()
