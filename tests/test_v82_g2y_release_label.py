"""G2Y build identifies itself consistently; do not mistake it for a prior release."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ['RAMSES_DB_PATH'] = str(Path(td)/'release_test.sqlite3')
        os.environ['RAMSES_ADMIN_USER'] = 'synthetic_release_owner'
        os.environ['RAMSES_ADMIN_PASSWORD'] = 'synthetic_release_owner_password'
        from bootstrap import initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        health = client.get('/health')
        assert health.status_code == 200
        assert 'G2Y' in health.json()['name'] and 'Test Only' in health.json()['name']
        html = client.get('/')
        assert html.status_code == 200 and 'V8.1E-G2Y' in html.text
        js = client.get('/static/app.js')
        assert js.status_code == 200 and 'V8.1E-G2Y' in js.text
        assert 'V8.1E-G2Y' in (ROOT/'START_Ramses_Mac.command').read_text()
        print('PASS G2Y development-only version label across HTTP, UI and Mac startup')


if __name__ == '__main__':
    run()
