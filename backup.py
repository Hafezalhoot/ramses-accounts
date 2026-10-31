"""Consistent SQLite online backup. Store backups outside the public web directory."""
import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from bootstrap import DB

p=argparse.ArgumentParser()
p.add_argument('--output-dir',default=str(Path(__file__).resolve().parent/'backups'))
args=p.parse_args()
dest_dir=Path(args.output_dir).expanduser().resolve();dest_dir.mkdir(parents=True,exist_ok=True)
if not DB.is_file():raise SystemExit('Database not found; initialize it first')
dest=dest_dir/f'ramses-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}.sqlite3'
with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as source, sqlite3.connect(dest) as target:
    source.backup(target)
os.chmod(dest,0o600)
print('Backup created:',dest)
