"""Verify a COPY of a SQLite snapshot, never mutate or restore a live database."""
import sqlite3
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("Usage: python3 scripts/check_backup.py /path/to/backup.sqlite3")
file = Path(sys.argv[1])
if not file.is_file():
    raise SystemExit("Backup file does not exist")
with sqlite3.connect(f"file:{file.resolve().as_posix()}?mode=ro", uri=True) as db:
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("FAILED: SQLite integrity check")
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='vouchers'").fetchone():
        raise SystemExit("FAILED: vouchers table missing")
    count = db.execute("SELECT COUNT(*) FROM vouchers").fetchone()[0]
print(f"PASS: backup valid. vouchers={count}")
