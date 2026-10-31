"""Synthetic test-only passphrase file for migration tests; never used in production."""
import os
from pathlib import Path


def configure(folder):
    key = Path(folder)/'test_only_upgrade_secret.txt'
    key.write_text('synthetic-test-archive-password-do-not-use-live')
    key.chmod(0o600)
    os.environ.pop('RAMSES_BACKUP_PASSPHRASE', None)
    os.environ['RAMSES_BACKUP_PASSPHRASE_FILE'] = str(key)
    return key
