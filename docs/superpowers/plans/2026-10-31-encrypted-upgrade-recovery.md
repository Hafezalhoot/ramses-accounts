# G2V encrypted upgrade implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or test-driven-development to implement and verify each step.

**Goal:** Replace durable plaintext migration snapshots with verified encrypted and restorable `.rbe` archives.

**Architecture:** Reuse G2M AES-GCM+Scrypt archive code. At the initialization preflight, detect known schema gaps and create exactly one encrypted pre-upgrade archive using the existing live SQLite connection, before SQL DDL. Fail closed without a passphrase; never overwrite archive or destination.

**Tech Stack:** Python 3, sqlite3, cryptography, standard library; source-owned script tests.

**Spec:** `docs/superpowers/specs/2026-10-31-encrypted-upgrade-recovery-design.md`

## Global constraints
- Synthetic databases only and NO-GO for production.
- Do not rewrite accounting records or fake missing V8.0 archive.
- Work in isolated branch; release ZIP only after source tests and archive verification.

## Review focus
1. Missing passphrase must not allow migrations.
2. WAL consistent snapshot and no plaintext durable archive.
3. Older pre-GL DB remains restorable and archive verification requires authenticated purpose.
4. Repeated initialization generates no duplicate backup.
5. Wrong key/corrupt archive/no-clobber fails safely.

## Task 1 — prove and fix pre-upgrade archive and migration guard
**Files:** `tests/test_v82_g2v_encrypted_upgrade.py`, `scripts/secure_backup.py`, `bootstrap.py`.
- [ ] Write failing tests for both historical V7.8 and original G2T schemas and key refusal.
- [ ] Observe a RED test against G2U source.
- [ ] Add connection-backed encrypted backup to G2M, metadata and legacy restore verification.
- [ ] Use one centralized preflight in `initialize()` for known missing tables/columns; no plaintext exports.
- [ ] GREEN test with fresh restore, second startup, tamper/wrong key tests.

## Task 2 — preserve compatibility and verify the full source suite
**Files:** Historical upgrade test fixtures, `scripts/ci_smoke.py`, release/readme docs.
- [ ] Update old migration assertions to encrypted backups and ensure test-owned passphrases.
- [ ] Run isolated regression scripts and entire source suite; classify genuine archive missing separately.
- [ ] Run CI smoke, compile, build/restore fresh release ZIP and SHA256.
- [ ] Review `git diff`, record explicit risks and next work.
