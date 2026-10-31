"""Read-only preflight for the owner's isolated Google Sheets staging mirror."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from google_sync import TABS, PREVIEW_STAGING_SHEET_ID, get_session, req


def main():
    key = ROOT / 'secrets' / 'service-account.json'
    if not key.is_file():
        raise SystemExit('Service account JSON not found: secrets/service-account.json')
    os.environ['RAMSES_ENVIRONMENT'] = 'free-preview'
    os.environ['GOOGLE_SHEET_ID'] = PREVIEW_STAGING_SHEET_ID
    os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'] = str(key)
    metadata = req(get_session(), 'GET',
                   f'https://sheets.googleapis.com/v4/spreadsheets/{PREVIEW_STAGING_SHEET_ID}',
                   params={'fields':'spreadsheetId,sheets(properties(title))'})
    titles = {s['properties']['title'] for s in metadata.get('sheets', [])}
    if metadata.get('spreadsheetId') != PREVIEW_STAGING_SHEET_ID or not set(TABS).issubset(titles):
        raise SystemExit('Google Sheets staging ID or required mirror tabs mismatch')
    print('PASS — Google service account can READ the isolated staging spreadsheet.')
    print('No Sheet content was modified; a real write sync must still be tested from the owner UI.')


if __name__ == '__main__':
    main()
