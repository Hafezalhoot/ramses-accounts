# Ramses Hospital Accounts V8.1E-G2M: recovery and financial control audit

**Build:** 31 October 2026  |  **Status:** DEVELOPMENT / TEST ONLY  |  **Production gate:** NO GO

## Executive summary

G2M continues G2L without changing historical patient invoices, vouchers, GL postings, fund opening approvals, POS settlement postings, or the database schema. The priority is survivability and accounting integrity: the previous scheduled snapshot was unencrypted, tied to the local host, and had only a limited check utility. A loss of the original server would therefore remain a severe risk.

The new encrypted backup utility creates an atomic, consistent SQLite online snapshot, encrypts it with AES-256-GCM, authenticates all ciphertext and metadata, verifies a full isolated recovery before publication, and refuses to overwrite an existing database on restore. It does NOT automatically replicate any file to another site; a backup sitting on the same computer remains vulnerable to disk failure, fire or ransomware. Temporary plaintext snapshots briefly exist inside a private directory; use an encrypted volume when handling real data. No real hospital data or live environment was used in these tests.

## Implemented changes

| Code / component | Verified change |
|---|---|
| `scripts/secure_backup.py` | Create/verify/restore encrypted `.rbe` SQLite snapshots, scrypt key derivation, authenticated AES-GCM with tamper detection, source and restored SQLite integrity + FK check, no-overwrite restore and private file permissions. |
| `tests/test_v81e_g2m_secure_backup.py` | Synthetic WAL-backed backup, full restore drill, no-clobber, wrong passphrase, altered ciphertext, truncation and insufficient key-file permissions. |
| `scripts/finance_preflight.py` | Read-only offline financial health report: SQLite integrity, foreign keys, GL trial balance, patient AR/advances/credits reconciliation, fund/bank/shift/POS source-ledger reconciliation. Returns nonzero status on differences. |
| `tests/test_v81e_g2m_finance_preflight.py` | Injects a balanced but unsupported cash GL journal and verifies independent reconciliation catches it without mutating data. |
| `START_Ramses_Mac.command` | Adds interactive encrypted backup and verification choices; boot dependency check now includes cryptography; version label corrected. |
| `Dockerfile` and `scripts/backup_encrypted_docker.sh` | Opt-in encrypted Docker backup using read-only file-based password at `/secrets/backup_passphrase`, encrypted output in `/backups/encrypted`; no password in command line. |
| `systemd/ramses-encrypted-backup.*` | Separate opt-in schedule for encrypted local staging; deliberately not auto-enabled or incorrectly described as an off-site backup. |
| `scripts/backup_local.sh` | Explicitly warns that the old snapshot is unencrypted and local. Its behavior remains backward compatible. |
| `static/app.js`, `static/index.html`, `app.py` | G2M release labels and permanent test-only warning; changing `RAMSES_ENVIRONMENT` alone can no longer make the UI claim the product is approved for live financial use. |
| `requirements.txt` | Adds vetted `cryptography` dependency for encrypted backup. |

## Verified tests (current development environment)

The **12 selected test scripts** in `QA_G2M_TEST_RESULTS.tsv` all returned PASS when run independently. They cover encryption/recovery, financial offline preflight, test-only banner, ledger integrity, patient controls, treasury reconciliation, POS, opening balances and concurrency, month close, account permissions and local server behavior. The current G2M delivery does NOT claim a rerun of the entire historical ~67-script suite. The previous V8.0 migration test remains blocked because the genuine archive has not been supplied as accessible bytes, even though its name is listed in Project Library.

No automatic Chromium or physical Mac hardware test was performed for the backup CLI. Mac launcher's Bash syntax was checked locally, and JavaScript was checked using Node. Dockerfile and opt-in systemd service were inspected; there was no live Docker host build or deployment in this test environment.

## Safe local usage (offline test database only)

The command-line utility will prompt for a strong passphrase when run interactively. To run unattended, create a private password file with mode `0600`, then set `RAMSES_BACKUP_PASSPHRASE_FILE` pointing to it. Never commit, email or put the password file in a release ZIP.

```bash
python3 -m pip install -r requirements.txt
python3 scripts/secure_backup.py create --db path/to/synthetic.sqlite3 --output-dir "$HOME/Ramses_Encrypted_Backups"
python3 scripts/secure_backup.py verify --input "$HOME/Ramses_Encrypted_Backups/NAME.rbe"
python3 scripts/secure_backup.py restore --input "$HOME/Ramses_Encrypted_Backups/NAME.rbe" --output-file "$HOME/ramses_recovery_drill.sqlite3"
python3 scripts/finance_preflight.py --db "$HOME/ramses_recovery_drill.sqlite3" --period 2026-08
```

Restoring to the running database path or overwriting an existing database is forbidden. Stop the application before any manually approved production recovery, preserve the original state and review the recovery plan with the financial owner.

Opt-in Docker staging, **only after** a file at `./secrets/backup_passphrase` is accessible to container UID 10001 and is mode `0600`:

```bash
/bin/sh scripts/backup_encrypted_docker.sh
```

The result is still in the **same host's** `/backups/encrypted` volume. Separately transfer it to secure physically independent storage, and perform periodic isolated full restore drills. A scheduled local backup is NOT proof of successful offsite disaster recovery.

## Current unresolved risks (NO GO)

1. Historical V8.0 migration fixture is present by title in Project Library but its bytes cannot be accessed here. Do not mark the migration test passed; the original ZIP must be attached to the chat or made accessible.
2. Patient care billing for inpatient/NICU/operations, inventory-cost/consumables, vendor AP, provider accruals, complete departmental P&L, insurer contracts and full role-scoped security remain incomplete.
3. POS gross/fee/net is recorded via approved settlements, but bank posting can occur before independently verified real bank arrival. Cross-month settlement-in-transit and chargebacks require a dedicated account and signoff workflow. Do not treat POS approval as bank arrival proof.
4. Backups are now technically encrypted and restorable on synthetic data, but **off-device retention, independent key custody, scheduled delivery monitoring and real hardware restore** remain operational acceptance gates.
5. The backup tool briefly stores a mode-0600 unencrypted scratch SQLite snapshot; on an unencrypted host disk, that is not complete at-rest protection.
6. The new version has not been checked end-to-end on real Ramses cashier terminals, with real financial signoff, a full workday of concurrent shifts, real bank CSVs or penetration tests. No real records were accessed or altered.

**Approval:** This ZIP is a development package, not a production release or a certification of complete financial/medical ERP correctness.
