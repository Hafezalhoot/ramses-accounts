"""Read-only, secret-free preflight for Ramses V7.8 test preview.

No changes to the hospital ledger, Sheets, existing passwords, or cloud systems.
"""
from __future__ import annotations
import argparse
import importlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = '1BIjVrtYUlt8lOtaarZPyz4Cci0XIp5eWIJwOCfUfTTk'
ORIGINAL = '1SJXFAvZ1BBpn9rQDccplpu5tL0yVFGJ1KOeyxDD0Kys'


def run(*, root: Path = ROOT, remote: bool = False) -> tuple[bool, list[str]]:
    """Check readiness without showing private credentials or patient/staff records."""
    root = Path(root)
    messages = []
    safe = True

    def note(ok, label, *, blocking=False):
        nonlocal safe
        messages.append(('OK   ' if ok else ('FAIL ' if blocking else 'INFO ')) + label)
        if blocking and not ok:
            safe = False

    note(all((root / item).is_file() for item in ('app.py', 'bootstrap.py', 'google_sync.py', 'shift_schedule.py', 'shift_coverage.py', 'schema.sql')),
         'Project files are complete', blocking=True)
    missing = []
    for module in ('fastapi', 'uvicorn', 'pydantic', 'httpx', 'openpyxl'):
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    note(not missing, 'Python requirements installed' if not missing else 'Missing dependencies: ' + ', '.join(missing),
         blocking=True)
    config_path = root / '.env'
    if not config_path.is_file():
        note(False, 'First-run .env not yet created; use the preview launcher before diagnostics')
    else:
        st = config_path.stat()
        note(not bool(stat.S_IMODE(st.st_mode) & 0o077),
             'Private config file is accessible only to its owner', blocking=True)
        # Only read the explicitly known key names. Do not print values.
        text = config_path.read_text(encoding='utf-8')
        vals = {}
        for raw in text.splitlines():
            if raw.strip() and not raw.lstrip().startswith('#') and '=' in raw:
                key, value = raw.split('=', 1)
                vals[key.strip()] = value.strip()
        has_owner = bool(vals.get('RAMSES_ADMIN_USER'))
        note(has_owner, 'Owner account name configured', blocking=True)
        if vals.get('GOOGLE_SHEET_ID'):
            note(vals['GOOGLE_SHEET_ID'] == STAGING,
                 'Google destination is the isolated test spreadsheet', blocking=True)
        else:
            note(True, 'No Google destination in .env (test runner hard-limits it to staging)')
        if ORIGINAL in text and not any(line.lstrip().startswith('#') for line in text.splitlines()
                                        if ORIGINAL in line):
            note(False, 'Original financial spreadsheet ID must not appear in active .env', blocking=True)

    demo_db = root / 'data' / 'free-preview.sqlite3'
    archive_db = root / 'data' / 'free-preview-archive.sqlite3'
    for dbpath in (demo_db, archive_db):
        if not dbpath.is_file():
            note(False, ('Archive' if dbpath == archive_db else 'Demo') + ' database not created yet; optional until first use')
            continue
        try:
            # Read-only SQLite URI: do not create/wipe or alter WAL state.
            c = sqlite3.connect(f'{dbpath.as_uri()}?mode=ro', uri=True, timeout=3)
            try:
                integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
                note(integrity == 'ok', 'SQLite integrity: ' + ('PASS' if integrity == 'ok' else 'FAILED'),
                     blocking=True)
                vouchers = c.execute('SELECT COUNT(*) FROM vouchers').fetchone()[0]
                archive = c.execute('SELECT COUNT(*) FROM legacy_entries').fetchone()[0]
                mode = 'ARCHIVE' if dbpath == archive_db else 'DEMO'
                note(True, f'{mode} test database: {vouchers} vouchers, {archive} archived rows')
                if dbpath == archive_db:
                    note(vouchers == 0, 'Historic archive cannot contain posted voucher transactions', blocking=True)
                # Redacted archive is allowed; identifiable archived rows are not.
                private = c.execute("""SELECT COUNT(*) FROM legacy_entries
                      WHERE coalesce(reference_no,'')!='' OR coalesce(employee_raw,'')!=''
                         OR coalesce(description,'') NOT IN ('','حركة أرشيفية - التفاصيل الشخصية محجوبة')""").fetchone()[0]
                note(private == 0, 'Archive records in this test are redacted', blocking=True)
            finally:
                c.close()
        except (sqlite3.Error, OSError) as exc:
            note(False, 'Could not verify preview SQLite: ' + type(exc).__name__, blocking=True)

    key = root / 'secrets' / 'service-account.json'
    if key.is_file():
        try:
            importlib.import_module('google.auth')
            note(True, 'Google API libraries installed')
        except ImportError:
            note(False, 'Google API libraries missing (pip install -r requirements.txt)', blocking=True)
        if os.name != 'nt':
            note(not bool(stat.S_IMODE(key.stat().st_mode) & 0o077),
                 'Google service-account key permissions are private', blocking=True)
        try:
            data = json.loads(key.read_text(encoding='utf-8'))
            valid = data.get('type') == 'service_account' and bool(data.get('private_key')) and bool(data.get('client_email'))
            note(valid, 'Google service-account key has required fields', blocking=True)
        except (ValueError, OSError, UnicodeError):
            note(False, 'Google service-account key format invalid', blocking=True)
        note(True, 'Actual Google API permission must still be checked with scripts/check_google_access.py')
    else:
        note(False, 'Google Sheets automatic sync not configured; local preview still works')
    executable = shutil.which('cloudflared')
    if executable:
        version = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=8)
        line = (version.stdout or version.stderr).splitlines()
        match = re.search(r'\b(\d{4}\.\d{1,2}\.\d+)\b', line[0]) if line else None
        note(version.returncode == 0, 'Cloudflare client installed' + (f' ({match.group(1)})' if match else ''))
    else:
        note(False, 'cloudflared not installed; private HTTPS link unavailable', blocking=remote)
    note(True, 'No changes were made to Google Sheets or financial data')
    return safe, messages


def main():
    parser = argparse.ArgumentParser(description='Read-only Ramses free-preview diagnostics')
    parser.add_argument('--remote', action='store_true', help='Require cloudflared')
    args = parser.parse_args()
    ok, messages = run(remote=args.remote)
    print('\nRamses V7.8 / FREE PREVIEW PRE-FLIGHT\n')
    for message in messages:
        print(message)
    print('\nRESULT:', 'Local prerequisites pass' if ok else 'Fix FAIL entries before using preview')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
