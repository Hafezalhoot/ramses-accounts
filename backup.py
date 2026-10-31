"""Legacy CLI compatibility: encrypted backups only (never plaintext snapshots).

Usage: python3 backup.py --output-dir /private/output
Passphrase: owner-only RAMSES_BACKUP_PASSPHRASE_FILE or interactive prompt.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from scripts.secure_backup import cli


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', default=str(Path(__file__).resolve().parent / 'backups' / 'encrypted'))
    p.add_argument('--db', default=None)
    args = p.parse_args()
    command = ['create', '--output-dir', args.output_dir]
    if args.db:
        command.extend(['--db', args.db])
    return cli(command)


if __name__ == '__main__':
    raise SystemExit(main())
