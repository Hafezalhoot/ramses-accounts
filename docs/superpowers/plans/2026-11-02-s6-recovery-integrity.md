# S6 Encrypted Recovery Integrity Implementation Plan

> For agentic workers: Execute inline with test-driven-development; no production data/actions.

**Goal:** Refuse encrypted accounting backups/restores that contain logically inconsistent posted GL or tampered stored evidence, and prove a logically isolated recovery drill.

**Architecture:** Reuse existing `scripts/secure_backup.py` archive format/CLI and `_verify_sqlite`. Add read-only financial/evidence checks before backup publication and after decryption, with compact regression scripts using synthetic SQLite only. No new schema, new cryptography, or live access.

**Tech Stack:** Python, sqlite3, AES-GCM existing dependency, FastAPI TestClient only for a smoke if useful.

**Spec:** Existing `RAMSES_G2P_MASTER_ROADMAP_TO_PRODUCTION_AR.md`, `README_S5_AR.md`, and `scripts/secure_backup.py` release gates.

## Global Constraints
- Preserve the V1 encrypted archive format; do not change user keys or existing database schema.
- Never overwrite a restore target, expose patient data or deploy.
- Distinguish a second local directory and subprocess from an actual separate physical device.
- Financial checks must be read-only; check *posted* journals only, with >1 lines and exact equality of debit and credit sums.
- Verify stored SQL evidence bytes against `file_size` and `sha256` for voucher and cashier shift attachments, and bank statement source digests.

## Review Focus
- Privileged database corruption that leaves SQLite integrity_check and FK checks green.
- Incorrect attachment hash or byte length despite valid SQLite rows.
- Incorrect bank source CSV bytes despite a retained digest.
- Snapshot restored to a new independent directory but unable to support an application boot.
- Wrong key or duplicate destination must fail closed (existing G2M regression).

### Task 1: Financial/evidence validation (RED/GREEN)
**Files:** `scripts/secure_backup.py`, `tests/test_s6_backup_financial_integrity.py`.
- [ ] Create synthetic posted journal fixture, intentionally corrupt it by privileged SQL and expect `_verify_sqlite` rejection.
- [ ] Run to observe assertion failure on S5.
- [ ] Add minimal grouped SQL query rejecting posted journals with missing lines, unequal totals; no DDL.
- [ ] Create mismatched attachment/bank payload tests, observe failures, then implement streaming rows with SHA-256 equality and byte lengths.
- [ ] Run targeted and historical G2M test.

### Task 2: Isolated disaster drill
**Files:** `tests/test_s6_backup_financial_integrity.py`.
- [ ] Seed synthetic voucher, posted journal and verified attachment; use CLI to create encrypted archive in A.
- [ ] Copy encrypted archive to distinct directory B, restore via new process with a private key file, compare exact row fingerprints on business-critical tables; check application can read restored DB; verify no source plaintext copied.
- [ ] Exercise refusal of overwrite, tamper, and missing key via historical G2M coverage.
- [ ] Run targeted tests + full CI smoke, record exact counts.

### Task 3: Package/verification
**Files:** `CURRENT_RELEASE.md`, `README_S6_AR.md`, source bundle and ZIP.
- [ ] Verify regression log and source status, commit on independent S6 branch.
- [ ] Create manifest and archive without secrets/runtime data; test ZIP integrity, extracted hashes and Git bundle clone.
- [ ] Report test-only NO-GO and remaining real hospital recovery/network/UAT gates.
