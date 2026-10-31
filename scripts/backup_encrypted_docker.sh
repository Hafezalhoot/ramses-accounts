#!/bin/sh
# Opt-in encrypted backup for a configured Docker staging host.
# Secrets stay in a read-only, user-owned /secrets/backup_passphrase file.
# Output still lives on THIS host until copied to independent storage.
set -eu
cd "$(dirname "$0")/.."
if [ ! -f secrets/backup_passphrase ]; then
  echo 'FAIL: Create secrets/backup_passphrase on the host, owned by UID 10001 with mode 600.' >&2
  exit 2
fi
if [ "$(stat -c '%a' secrets/backup_passphrase 2>/dev/null || stat -f '%Lp' secrets/backup_passphrase)" != '600' ]; then
  echo 'FAIL: Passphrase file must have mode 600.' >&2
  exit 2
fi
docker compose exec -T -e RAMSES_BACKUP_PASSPHRASE_FILE=/secrets/backup_passphrase \
  ramses-accounts python /app/scripts/secure_backup.py create --db /data/ramses.sqlite3 --output-dir /backups/encrypted
printf '\nCopy the .rbe output to a physically independent secure location. The host volume alone is not off-site recovery.\n'
