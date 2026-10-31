#!/bin/sh
# Consistent on-line SQLite snapshot inside the running container.
# These local snapshots are NOT your off-device / encrypted disaster recovery copy.
set -eu
cd "$(dirname "$0")/.."
echo 'NOTICE: This is a plaintext LOCAL snapshot, not an encrypted off-site backup.' >&2
docker compose exec -T ramses-accounts python backup.py --output-dir /backups
