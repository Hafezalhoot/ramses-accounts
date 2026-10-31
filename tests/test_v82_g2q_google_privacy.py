"""F-014 regression: production/staging payroll/audit mirror requires explicit opt-in.

Uses synthetic SQLite and a network-call trap, never contacts Google.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ['RAMSES_DB_PATH'] = str(Path(td) / 'synthetic.sqlite3')
        os.environ['RAMSES_ADMIN_USER'] = 'owner'
        os.environ['RAMSES_ADMIN_PASSWORD'] = 'test_only_owner_password_2026'
        os.environ['RAMSES_ENVIRONMENT'] = 'staging'
        os.environ['GOOGLE_SHEET_ID'] = 'private_synthetic_google_sheet'
        os.environ.pop('RAMSES_GOOGLE_SYNC_SENSITIVE_APPROVED', None)
        from bootstrap import initialize, connect
        initialize()
        import google_sync
        calls = []
        def trap():
            calls.append('network')
            raise RuntimeError('No outside network allowed in this test')
        with connect() as c, patch.object(google_sync, 'get_session', side_effect=trap):
            try:
                google_sync.sync_to_google(c)
            except ValueError as error:
                assert 'RAMSES_GOOGLE_SYNC_SENSITIVE_APPROVED' in str(error), str(error)
            else:
                raise AssertionError('Sensitive Google mirror enabled without explicit approval')
        assert calls == [], 'Consent check must run before any Google request'
        os.environ['RAMSES_GOOGLE_SYNC_SENSITIVE_APPROVED'] = '1'
        try:
            with connect() as c, patch.object(google_sync, 'get_session', side_effect=trap):
                try:
                    google_sync.sync_to_google(c)
                except RuntimeError as error:
                    assert 'No outside network' in str(error)
                else:
                    raise AssertionError('Approved export should attempt the normal connection flow')
            assert calls == ['network']
        finally:
            os.environ.pop('RAMSES_GOOGLE_SYNC_SENSITIVE_APPROVED', None)
        print('PASS G2Q Google sync requires deliberate privacy approval before any external network call')


if __name__ == '__main__':
    run()
