#!/bin/sh
# Compatibility entrypoint for systemd: now fail-closed, encrypted backups only.
# Set up secrets/backup_passphrase mode 600; stage encrypted archives off-device.
set -eu
cd "$(dirname "$0")/.."
exec /bin/sh scripts/backup_encrypted_docker.sh
