"""Run a no-cost, temporary, email-protected V8.1C preview from your own PC.

No domain, GitHub Actions, Render, or paid VPS required. This is NOT a 24/7 host.
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING_ID = '1BIjVrtYUlt8lOtaarZPyz4Cci0XIp5eWIJwOCfUfTTk'


def load_private_config(path: Path) -> dict:
    config = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise RuntimeError('Invalid .env line')
        key, value = line.split('=', 1)
        key = key.strip()
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            raise RuntimeError('Invalid environment variable name')
        config[key] = value.strip()
    return config


def preview_environment(local_only=False, *, archive_mode=False) -> dict:
    envfile = ROOT / '.env'
    if not envfile.is_file():
        subprocess.run([sys.executable, str(ROOT/'scripts'/'setup_local.py')], cwd=ROOT, check=True)
    values = load_private_config(envfile)
    preview_db = ROOT / 'data' / ('free-preview-archive.sqlite3' if archive_mode else 'free-preview.sqlite3')
    if len(values.get('RAMSES_ADMIN_PASSWORD', '')) < 16:
        dbfile = preview_db
        if not dbfile.is_file():
            raise RuntimeError('Initial password missing from .env; cannot create a new owner')
    for name in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON'):
        # A modified .env cannot point this trial at the REAL owner sheet.
        if name in values and name == 'GOOGLE_SHEET_ID' and values[name] != STAGING_ID:
            raise RuntimeError('This preview can write ONLY to the isolated staging Google Sheet')
    env = dict(os.environ)
    env.update(values)
    env['RAMSES_ENVIRONMENT'] = 'free-preview'
    env['RAMSES_SECURE_COOKIES'] = '0' if local_only else '1'
    env['RAMSES_DB_PATH'] = str(preview_db)
    env.pop('GOOGLE_SHEET_ID', None)
    env.pop('GOOGLE_SERVICE_ACCOUNT_JSON', None)
    # Auto-enable mirror only when the user has privately installed a valid JSON key.
    key = ROOT / 'secrets' / 'service-account.json'
    if key.is_file():
        if os.name != 'nt' and stat.S_IMODE(key.stat().st_mode) & 0o077:
            raise RuntimeError('Service-account JSON must be private: run chmod 600 secrets/service-account.json')
        env['GOOGLE_SHEET_ID'] = STAGING_ID
        env['GOOGLE_SERVICE_ACCOUNT_JSON'] = str(key)
    return env


def init_database(env: dict, legacy_path: Path | None) -> bool:
    dbpath = Path(env['RAMSES_DB_PATH'])
    first = not dbpath.exists()
    if legacy_path and not legacy_path.is_file():
        raise FileNotFoundError('Excel historical file not found: ' + str(legacy_path))
    if legacy_path and not first:
        import sqlite3
        with sqlite3.connect(dbpath) as current:
            if current.execute('SELECT COUNT(*) FROM vouchers').fetchone()[0]:
                raise RuntimeError('This trial already contains voucher transactions. Use a NEW extracted ZIP folder to review the historic financial archive separately.')
    old_env = dict(os.environ)
    try:
        os.environ.clear(); os.environ.update(env)
        sys.path.insert(0, str(ROOT))
        from bootstrap import initialize
        # Existing SQLite DB is never replaced; historical import uses INSERT OR IGNORE.
        initialize(str(legacy_path) if legacy_path else None)
    finally:
        os.environ.clear(); os.environ.update(old_env)
    return first


def await_local_health(port: int, process: subprocess.Popen, seconds=15) -> None:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError('Local application exited before health became ready')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                if response.status == 200: return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.3)
    raise RuntimeError('Local application did not become ready')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Safe, free Ramses trial on your existing computer')
    parser.add_argument('--email', default='', help='Exact email allowed to enter the HTTPS tunnel')
    parser.add_argument('--local-only', action='store_true', help='Run only on this PC (no Internet URL)')
    parser.add_argument('--demo', action='store_true', help='Seed 3 fabricated financial vouchers on a NEW trial')
    parser.add_argument('--legacy', type=Path, help='Optional Excel for read-only, redacted June archive')
    parser.add_argument('--archive', action='store_true', help='Load the bundled anonymized 618-row June financial archive')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args(argv)
    if int(args.demo)+int(bool(args.legacy))+int(args.archive) > 1:
        parser.error('Choose just one of --demo, --archive, --legacy')
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535')
    if not args.local_only:
        if not re.fullmatch(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}', args.email):
            parser.error('An exact --email is required for the protected Cloudflare URL')
        if not shutil.which('cloudflared'):
            parser.error('cloudflared is not installed. See FREE_PREVIEW_AR.md or use --local-only')
    env = preview_environment(local_only=args.local_only, archive_mode=bool(args.archive or args.legacy))
    archive = ROOT/'imports'/'REDACTED_JUNE_2026_PREVIEW.xlsx' if args.archive else args.legacy
    first = init_database(env, archive)
    if args.demo and not first:
        import sqlite3
        with sqlite3.connect(env['RAMSES_DB_PATH']) as c:
            if c.execute('SELECT COUNT(*) FROM legacy_entries').fetchone()[0]:
                raise RuntimeError('Archive and demo entries must be kept in separate trial folders.')
    if args.demo and first:
        old_env = dict(os.environ)
        try:
            os.environ.clear(); os.environ.update(env)
            from seed_preview_demo import seed_demo
            result = seed_demo(ROOT, env['RAMSES_ADMIN_PASSWORD'])
            print('Demo vouchers created:', result.get('seeded'))
            print('Demo reviewer username:', result.get('reviewer_username'))
            print('Demo reviewer ONE-TIME password:', result.get('reviewer_password'))
        finally:
            os.environ.clear(); os.environ.update(old_env)
    elif args.demo:
        print('Existing preview database kept unchanged. Sample seeding is only for a new database.')
    child = None
    tunnel = None
    # Closing the Terminal or stopping the launcher must also stop the public tunnel.
    # Without this, SIGTERM can leave the origin and email-protected tunnel running.
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    def _stop_preview(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _stop_preview)
    try:
        child = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app:app',
                                  '--host', '127.0.0.1', '--port', str(args.port)],
                                 cwd=ROOT, env=env)
        await_local_health(args.port, child)
        print('\nLocal preview server ready. SQLite stays on THIS computer only.')
        if args.local_only:
            print(f'Open: http://127.0.0.1:{args.port}/')
        else:
            print('Starting email-protected HTTPS tunnel. Copy the trycloudflare.com URL below.')
            print('Only the allowed email receives the one-time PIN; then sign in to Ramses.')
            tunnel = subprocess.Popen(['cloudflared', 'tunnel', '--url',
                                        f'http://127.0.0.1:{args.port}', '--allowed-mail', args.email],
                                       cwd=ROOT)
            time.sleep(1.5)
            if tunnel.poll() is not None:
                raise RuntimeError('The cloudflared tunnel stopped early. Check that your version supports --allowed-mail.')
        print('Press Ctrl+C to stop and revoke this temporary link.')
        while child.poll() is None and (tunnel is None or tunnel.poll() is None):
            time.sleep(0.6)
        raise RuntimeError('Preview process ended; remote preview is now closed')
    except KeyboardInterrupt:
        print('\nPreview stopped. Financial data remains only in your local preview DB.')
    finally:
        for process in (tunnel, child):
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == '__main__':
    main()
