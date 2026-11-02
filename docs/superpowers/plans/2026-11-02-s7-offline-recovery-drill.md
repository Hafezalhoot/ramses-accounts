# S7 Offline Recovery Drill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Create a safe, offline, operator-run recovery drill to make a genuine external-device rehearsal executable, without claiming to have performed one.

**Architecture:** Reuse `scripts/secure_backup.py` validation; new isolated CLI orchestrates SHA256, no-clobber restore and read-only separate-process app smoke; standalone regression exercises successful and negative cases.

**Tech Stack:** Python 3, stdlib, SQLite, existing FastAPI TestClient/cryptography.

**Spec:** `docs/project-autopilot/S7_OFFLINE_RECOVERY_SPEC.md`

## Global Constraints
- Only synthetic test data; no production DB or network actions.
- Never persist passphrase, patient data or login credentials in reports.
- No automatic overwrites or database switchover, no extra dependency.
- Hospital production remains NO-GO pending real device and human signoffs.

## Review Focus
- A wrongly copied ciphertext: reject before generating persistent plaintext.
- Incorrect passphrase or modified AES-GCM: fail and securely remove failed output path.
- Existing path/symlink: refuse rather than clobber.
- Post-decryption app unable to start: fail drill with no accepted report.
- No private financial information in generated report.

### Task 1: CLI and acceptance test
**Files:** create `tests/test_s7_recovery_drill.py`, `scripts/recovery_drill.py`; modify `scripts/ci_smoke.py`.

- [x] RED: synthetic encrypted backup, expected SHA, new output dir and separate process app read-only smoke must succeed; wrong SHA/wrong key/tampering/existing destination must not leave a new DB.
- [x] Execute red to see expected failure (missing CLI).
- [x] Implement minimal CLI using `scripts.secure_backup.verify_or_restore()` and child `TestClient` with no live DB side effects.
- [x] GREEN: execute new acceptance and prior S6/G2M source tests; add test to CI list.

### Task 2: Operator documentation and release verification
**Files:** create `README_S7_AR.md`, update `CURRENT_RELEASE.md`, `PROJECT_AUTOPILOT_STATE_AR.md`, `docs/project-autopilot/{PROJECT_STATUS,ROADMAP,TEST_REPORT}.md`.

- [x] Run CI and relevant older integration tests; report actual counts including SKIP/BLOCKED.
- [x] Explain exact executable second-device runbook and manual IT/finance signoff; never claim off-device success from a simulated path.
- [x] Package ZIP and source-history Git bundle only after verifying source, exact archive contents, and QA evidence.
