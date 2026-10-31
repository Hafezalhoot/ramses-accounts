# G2V encrypted upgrade safety — design

## Context
G2U initialization creates four durable plaintext SQLite rollback files for historical upgrades and does not snapshot G2T-to-G2U. The regular G2M encrypted backup CLI already supports AES-256-GCM, integrity checking, passphrase file permissions and safe no-clobber restores.

## Goal
For existing database schema upgrades, always create a consistent, encrypted, verified rollback archive *before* modifying the application schema. A missing/insecure key or invalid encrypted archive blocks migration. Retain ability to restore historical pre-GL schemas safely to a new DB path.

## Chosen approach
Reuse `scripts/secure_backup.py` for cryptography, temporary isolation and restore verification; call a new connection-backed encrypted snapshot helper from `bootstrap.initialize()` once when an explicit schema difference is detected. No cryptography rewrite or external service. Known G2U versions require no new backup upon an unchanged restart.

## Rejected alternatives
- Keep plaintext pre-upgrade `.sqlite3` snapshots (exposes employee and patient financial records).
- Silently skip backup when key missing (risks un-recoverable migrations).
- Auto-upload off-site (no user-authorized storage destination or retention policy).

## Constraints and acceptance
- No live deployment, personal data, real banking, DB-in-place restore or production change.
- Tests with synthetic legacy V7.8 fixture and frozen G2T schema, both before and after migration, in separate temporary DBs.
- `.rbe` encrypted, authenticated, permission `0600`, private directory `0700`; no durable `.sqlite3` backup file; snapshot temp files are cleaned.
- With no key: migration refuses, pre-upgrade schema and data remain unchanged, and no plaintext rollback survives.
- Restore to distinct nonexistent database is verified; wrong key, corruption and destination overwrite fail without changing files.
- Real V8.0 ZIP still missing and is never replaced by a simulated archival baseline.
- Temporary plaintext SQLite inside the private working directory is an existing G2M limitation, not a claim of zero plaintext disk exposure; deployment requires an encrypted filesystem and independent off-site custody.
