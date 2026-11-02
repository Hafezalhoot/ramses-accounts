"""Offline, copy-only Ramses disaster recovery rehearsal (NO production switchover).

On a separate encrypted workstation with an independently supplied .rbe
archive and its private decryption key:

  python scripts/recovery_drill.py --archive /secure/backup.rbe \
    --expected-sha256 THE_64_HEX_DIGEST_FROM_SOURCE_DEVICE \
    --output-dir /encrypted_disk/NEW_RECOVERY_DIRECTORY

Restores only to a new directory, runs a no-credential TestClient smoke in a
separate process against a DISPOSABLE copy, and writes a PHI-free JSON report.
This CLI does NOT prove second-device usage; an IT officer must attest that.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from secure_backup import verify_or_restore

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()


def _isolated_smoke(restored: Path, workspace: Path) -> dict:
    # App `connect()` enables WAL; NEVER run it against the archival restore.
    # A disposable copy permits checking routing and deny-by-default without
    # mutating the certified recovered bytes.
    with tempfile.TemporaryDirectory(prefix='.ramses-smoke-', dir=workspace) as folder:
        disposable = Path(folder) / 'smoke.sqlite3'
        shutil.copyfile(restored, disposable)
        os.chmod(disposable, 0o600)
        env = os.environ.copy()
        for name in list(env):
            if name.startswith(('GOOGLE_', 'RAMSES_')):
                env.pop(name, None)
        env['RAMSES_DB_PATH'] = str(disposable)
        env['RAMSES_ENVIRONMENT'] = 'staging'
        env['PYTHONPATH'] = str(ROOT)
        # The subprocess must boot the actual FastAPI app, not just run PRAGMA.
        # It has no passphrase, operator login or network call.
        check = '''import json, sqlite3\nfrom fastapi.testclient import TestClient\nfrom bootstrap import DB\nfrom app import app\nwith sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True) as c:\n    c.execute("PRAGMA query_only=ON")\n    assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 1\nwith TestClient(app) as client:\n    health = client.get("/health").status_code\n    unauth = client.get("/api/me").status_code\nprint(json.dumps({"app_health_http_status":health,"unauthenticated_api_http_status":unauth}))\nassert health == 200 and unauth == 401\n'''
        run = subprocess.run([sys.executable, '-c', check], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=65)
        if run.returncode:
            # Never include stderr: it may contain local file paths or data.
            raise ValueError('Isolated FastAPI recovery smoke failed')
        try:
            statuses = json.loads(run.stdout.strip())
        except json.JSONDecodeError:
            raise ValueError('Recovery smoke produced invalid status') from None
        if statuses != {'app_health_http_status':200, 'unauthenticated_api_http_status':401}:
            raise ValueError('Recovery smoke returned unexpected status')
        return statuses


def drill(archive: Path, expected: str, output: Path) -> dict:
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
        raise ValueError('Expected archive SHA-256 must be 64 hexadecimal characters')
    if not archive.is_file():
        raise ValueError('Encrypted archive not found')
    if output.exists() or output.is_symlink():
        raise ValueError('Refusing to use an existing recovery directory')
    if not output.parent.is_dir():
        raise ValueError('Recovery parent directory does not exist')
    actual = sha256_file(archive)
    if not secrets.compare_digest(actual, expected.lower()):
        raise ValueError('Transferred archive SHA-256 does not match source digest')
    # A fresh, private directory only; never reuse or modify an existing DB.
    output.mkdir(mode=0o700)
    try:
        if os.name == 'posix' and (output.stat().st_mode & 0o077):
            raise ValueError('Recovery directory must be owner-only (0700)')
        restored = output / 'recovered.sqlite3'
        # Bind both operations to the same copied ciphertext. Hashing one
        # external path then opening it again leaves a local TOCTOU window:
        # another *valid* AES archive can replace it between those operations.
        with tempfile.TemporaryDirectory(prefix='.ramses-input-', dir=output) as staged:
            stable_archive = Path(staged) / 'authenticated-source.rbe'
            shutil.copyfile(archive, stable_archive)
            os.chmod(stable_archive, 0o600)
            if not secrets.compare_digest(sha256_file(stable_archive), actual):
                raise ValueError('Encrypted archive changed after SHA-256 transfer check')
            summary = verify_or_restore(stable_archive, restored)
        recovered_digest = sha256_file(restored)
        smoke = _isolated_smoke(restored, output)
        if sha256_file(restored) != recovered_digest:
            raise ValueError('Restored database changed during isolated smoke')
        # No identifying names, source paths, monetary figures or credentials.
        report = {
            'status': 'PASS', 'mode': 'OFFLINE_COPY_ONLY_RECOVERY_DRILL',
            'generated_utc': datetime.now(timezone.utc).isoformat(),
            'archive_sha256': actual, 'restored_sha256': recovered_digest,
            'financial_integrity': 'PASS', 'sqlite_integrity': 'PASS',
            'copy_only_no_production_switchover': True,
            'physical_off_device_drill_verified': False,
            'independent_hospital_it_signoff_required': True,
            **smoke,
        }
        # Verify returned summary used the Ramses validator, without
        # exposing counts (patients, staff, cash movements) in report.
        if not isinstance(summary, dict) or 'users' not in summary:
            raise ValueError('Restore returned unexpected integrity summary')
        result = output / 'recovery_report.json'
        with result.open('x', encoding='utf-8') as dest:
            os.chmod(result, 0o600)
            json.dump(report, dest, indent=2, sort_keys=True)
            dest.write('\n')
            dest.flush()
            os.fsync(dest.fileno())
        return report
    except BaseException:
        # Remove ONLY the just-created recovery directory. A failure must not
        # leave a plaintext accounting DB or a misleading PASS report.
        shutil.rmtree(output)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        report = drill(args.archive.expanduser().absolute(), args.expected_sha256,
                       args.output_dir.expanduser().absolute())
        print(json.dumps(report, sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        # Do not leak traceback, local PII or secret contents.
        print('FAIL: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
