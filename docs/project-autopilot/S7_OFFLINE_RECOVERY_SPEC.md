# S7 — Portable offline disaster-recovery rehearsal (TEST_ONLY)

## Goal
Allow hospital IT to run a **manual, offline, copy-only** recovery drill on a *different computer* using a copied encrypted `.rbe` backup and independently supplied recovery passphrase. Produce verifiable, non-sensitive status, and never modify or replace the operating hospital database. This project session can only test a **simulated separate machine** in the container, NOT assert real off-device success.

## Selected approach and alternatives
- Selected: small stdlib wrapper around current `scripts/secure_backup.py` verified restore, then separately spawned read-only FastAPI `/health` and unauthorized `/api/me` checks. Avoid duplicating AES/SQL validation and never open actual hospital production DB.
- Rejected: automatically copying real backup to cloud / sharing patient data; unapproved transmission, credentials and data residency.
- Rejected: changing live launcher or automatically switching the app's DB path; this is an approval-sensitive cutover.

## User acceptance
1. `python scripts/recovery_drill.py --archive ARCHIVE.rbe --expected-sha256 64_HEX --output-dir NEW_DIRECTORY` works on a test archive when `RAMSES_BACKUP_PASSPHRASE_FILE` points to a private local passphrase file. It checks SHA256 on a private staged copy **before** decrypting the very same bytes and invokes existing authenticated, financially validated restore, then checks the restored DB using a separate Python process with FastAPI TestClient, `/health` 200 and `/api/me` 401 with no auth cookie.
2. Output is a newly created owner-private directory with recovered DB mode 0600 and a JSON report with archive digest, database digest, offline smoke statuses, and *no patient records, passwords, names, session tokens, transaction values or identifying source path*.
3. Wrong archive hash, incorrect passphrase, corrupt archive, missing archive, and pre-existing output directory all fail without overwriting anything; on failures, remove newly created sensitive directory and decrypted contents.
4. Never reinitialize an existing DB, execute a migration, contact network, copy keys, bypass encryption, or mark actual hospital IT signoff done.
5. Existing S6 integrity checks remain the authoritative SQL/financial validation; no new financial policy introduced.

## Gates
- Local acceptance: failing test before implementation (RED); successful positive/negative tests after (GREEN).
- Source CI and previous backup/financial integration regressions.
- Operator-run physical offsite rehearsal, original V8.0 migration, hospital UAT/signoffs remain BLOCKED/NO-GO until independently evidenced.
