"""Missing runtime storage must return 503 without creating a new ledger."""
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s12-runtime-') as folder:
        root=Path(folder)
        path=root/'mount'/'synthetic ledger #? عربية.sqlite3'
        os.environ.update(RAMSES_DB_PATH=str(path),RAMSES_ADMIN_USER='s12_owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_s12_runtime_password_long')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize,connect
        from app import app
        from fastapi.testclient import TestClient
        initialize()  # Only explicit initialization may create storage.
        owner=TestClient(app)
        login={'username':'s12_owner','password':'synthetic_s12_runtime_password_long'}
        assert owner.post('/api/login',json=login).status_code==200
        with connect() as c:
            before={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                    for t in ('users','sessions','vouchers','audit_log','gl_journals')}
        # Move the whole mount, including SQLite WAL/SHM sidecars. Moving only
        # the main file would be an invalid restore simulation and lose WAL data.
        held=root/'retained-original-storage'
        path.parent.rename(held)
        for client in (TestClient(app,raise_server_exceptions=False),owner):
            result=client.get('/api/me')
            assert not path.exists() and not path.parent.exists(), 'Request recreated missing ledger storage'
            assert result.status_code==503,result.text
            assert client.post('/api/login',json=login).status_code==503
            assert not path.parent.exists(), 'Login created a replacement database directory'
            assert client.get('/health').status_code==503
        # Deliberately restoring the original storage recovers existing sessions
        # and does not create users, journals or a replacement ledger.
        held.rename(path.parent)
        assert owner.get('/api/me').status_code==200
        assert owner.get('/health').status_code==200, 'Readiness must encode special SQLite URI characters'
        with connect(create=False) as c:
            assert before=={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before}
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS S12 runtime DB: missing storage 503, no file/directory creation, original restored intact, safe SQLite URI')


if __name__=='__main__':
    run()
