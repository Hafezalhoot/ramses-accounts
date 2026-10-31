"""Sanitization and strict staging-only Google sync safeguards for free trial."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))


def run():
    if not (ROOT/'imports'/'REDACTED_JUNE_2026_PREVIEW.xlsx').is_file():
        print('SKIP: private June historical workbook intentionally excluded from development ZIP')
        return
    from google_sync import verify_preview_sheet, PREVIEW_STAGING_SHEET_ID
    from free_preview import preview_environment
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        os.environ['RAMSES_ENVIRONMENT']='free-preview'
        os.environ['GOOGLE_SHEET_ID']='1SJXFAvZ1BBpn9rQDccplpu5tL0yVFGJ1KOeyxDD0Kys'
        try:
            verify_preview_sheet()
            raise AssertionError('Original ledger must be protected')
        except ValueError:
            pass
        os.environ['GOOGLE_SHEET_ID'] = PREVIEW_STAGING_SHEET_ID
        verify_preview_sheet()
        os.environ['RAMSES_DB_PATH']=str(tmp/'preview.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='test_preview_only_long_password'
        from bootstrap import initialize,connect
        initialize(str(ROOT/'imports'/'REDACTED_JUNE_2026_PREVIEW.xlsx'))
        with connect() as c:
            assert c.execute('SELECT count(*) FROM legacy_entries').fetchone()[0] == 618
            assert c.execute('SELECT count(*) FROM fund_movements').fetchone()[0] == 0
            assert c.execute('SELECT count(*) FROM vouchers').fetchone()[0] == 0
            assert c.execute("SELECT count(*) FROM legacy_entries WHERE reference_no!='' OR employee_raw!=''").fetchone()[0] == 0
            assert c.execute('SELECT count(distinct description) FROM legacy_entries').fetchone()[0] == 1
        print('PASS - isolated free-preview archive, 618 redacted entries, original sheet blocked')


if __name__ == '__main__': run()
