"""Audit failure must roll back new users, employees, funds and their GL map."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s11-atomic-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='s11_owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_s11_owner_password_long')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize, connect
        from app import app
        from fastapi.testclient import TestClient
        initialize()
        owner = TestClient(app)
        login = owner.post('/api/login', json={'username':'s11_owner',
                            'password':'synthetic_s11_owner_password_long'})
        assert login.status_code == 200, login.text
        headers = {'X-CSRF-Token':login.json()['csrf']}
        cases = [('/api/users', {'username':'audit_staff','role':'reviewer',
                  'password':'synthetic_staff_password_long'}, 'users', 'username', 'audit_staff', 'create_user'),
                 ('/api/employees', {'code':'AUDIT_STAFF','name':'Synthetic audit staff'},
                  'employees','code','AUDIT_STAFF','create_employee'),
                 ('/api/funds', {'code':'audit_cash','name':'Synthetic audit drawer','kind':'cash'},
                  'funds','code','audit_cash','create_fund')]
        # A real SQLite failure, not a mocked audit function: statements before
        # the failed INSERT must roll back along with sync/GL side effects.
        with connect() as c:
            c.execute('''CREATE TRIGGER synthetic_audit_failure BEFORE INSERT ON audit_log
              WHEN NEW.action IN ('create_user','create_employee','create_fund')
              BEGIN SELECT RAISE(ABORT,'synthetic audit storage failure'); END''')
            counts = {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                      for t in ('gl_accounts','gl_fund_accounts','audit_log')}
            revision = c.execute('SELECT revision FROM sync_status WHERE id=1').fetchone()[0]
        failures = []
        for endpoint, body, table, key, value, action in cases:
            response = owner.post(endpoint, headers=headers, json=body)
            assert response.status_code >= 400, response.text
            with connect() as c:
                if c.execute(f'SELECT COUNT(*) FROM {table} WHERE {key}=?',(value,)).fetchone()[0]:
                    failures.append(endpoint+' persisted an unaudited entity')
        with connect() as c:
            after = {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in counts}
            if counts != after: failures.append('GL/audit side effects survived: '+str(after))
            assert c.execute('SELECT revision FROM sync_status WHERE id=1').fetchone()[0] == revision
        assert not failures, failures
        with connect() as c:
            c.execute('DROP TRIGGER synthetic_audit_failure')
        for endpoint, body, table, key, value, action in cases:
            response = owner.post(endpoint, headers=headers, json=body)
            assert response.status_code == 200, response.text
            entity_id = response.json()['id']
            with connect() as c:
                assert c.execute(f'SELECT id FROM {table} WHERE {key}=?',(value,)).fetchone()[0] == entity_id
                assert c.execute('SELECT COUNT(*) FROM audit_log WHERE action=? AND entity_id=?',
                                 (action,str(entity_id))).fetchone()[0] == 1
            duplicate = owner.post(endpoint, headers=headers, json=body)
            assert duplicate.status_code == 400, duplicate.text
        with connect() as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS S11 atomic master data: audit failure rolls back all 3 entities + GL, retry once, duplicate denied')


if __name__ == '__main__':
    run()
