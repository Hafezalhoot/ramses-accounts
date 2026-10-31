"""Small self-check: atomic mirror request, allowlist and non-lossy error handling."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Response:
    def __init__(self, data):
        self.data = data
        self.content = b'{}'

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class MockGoogle:
    def __init__(self, tabs, fail_write=False):
        self.calls = []
        self.tabs = tabs
        self.fail_write = fail_write

    def request(self, method, url, **options):
        self.calls.append((method, url, options))
        if method == 'GET':
            return Response({'spreadsheetId': 'private_sheet_test', 'sheets': [
                {'properties': {'title': name, 'sheetId': sid,
                                'gridProperties': {'rowCount': 3, 'columnCount': 20}}}
                for name, sid in self.tabs.items()]})
        if self.fail_write:
            raise ConnectionError('offline Google')
        return Response({'replies': [{}] * len(options['json']['requests'])})


def run():
    with tempfile.TemporaryDirectory() as temp:
        os.environ['RAMSES_DB_PATH'] = str(Path(temp) / 'hospital.sqlite3')
        os.environ['RAMSES_ADMIN_USER'] = 'owner'
        os.environ['RAMSES_ADMIN_PASSWORD'] = 'test_only_password_16plus'
        os.environ['GOOGLE_SHEET_ID'] = 'private_sheet_test'
        from bootstrap import initialize, connect
        import google_sync

        legacy = ROOT / 'imports' / 'legacy_june_2026.xlsx'
        initialize(str(legacy) if legacy.is_file() else None)
        allowed_tabs = {name: 101 + index for index, name in enumerate(google_sync.TABS)}
        allowed_tabs['Owner_Private_Dashboard'] = 999
        mock = MockGoogle(allowed_tabs)
        with patch.object(google_sync, 'get_session', return_value=mock):
            c = connect()
            try:
                counts = google_sync.sync_to_google(c)
            finally:
                c.close()
        assert counts['Ramses_Vouchers'] == 0
        assert counts['Ramses_Funds'] == 4
        assert len(mock.calls) == 2 and [method for method, _, _ in mock.calls] == ['GET', 'POST']
        operations = mock.calls[1][2]['json']['requests']
        assert all(list(op) == ['appendDimension'] or list(op) == ['updateCells'] or list(op) == ['repeatCell'] for op in operations)
        assert 'batchClear' not in str(mock.calls) and 'values:batchUpdate' not in str(mock.calls)
        assert '999' not in str(operations)  # owner-owned dashboard is never modified
        ids_written = {op['updateCells']['start']['sheetId'] for op in operations if 'updateCells' in op}
        assert ids_written == set(allowed_tabs.values()) - {999}
        assert any('repeatCell' in op for op in operations)  # stale rows cleared atomically
        assert any('appendDimension' in op for op in operations)  # space for 4 funds
        assert google_sync.cell('=IMPORTDATA("https://example.com")') == {
            'userEnteredValue': {'stringValue': '=IMPORTDATA("https://example.com")'}}

        no_tab = MockGoogle({name: sid for name, sid in allowed_tabs.items()
                             if name != 'Ramses_Payroll'})
        with patch.object(google_sync, 'get_session', return_value=no_tab):
            c = connect()
            try:
                try:
                    google_sync.sync_to_google(c)
                    assert False, 'missing tab must fail closed'
                except ValueError as exc:
                    assert 'Ramses_Payroll' in str(exc)
            finally:
                c.close()
        assert len(no_tab.calls) == 1  # no writes at all

        failing = MockGoogle(allowed_tabs, fail_write=True)
        with patch.object(google_sync, 'get_session', return_value=failing):
            c = connect()
            try:
                try:
                    google_sync.sync_to_google(c)
                    assert False, 'failure should be reported'
                except ConnectionError:
                    pass
            finally:
                c.close()
        assert len(failing.calls) == 2  # one attempted atomic write, zero destructive pre-clears
        print('PASS - atomic private mirror, no pre-clear, preserved owner tabs, failures are safe')


if __name__ == '__main__':
    run()
