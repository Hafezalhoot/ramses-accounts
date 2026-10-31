# G3B Clinical Document Fingerprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development or test-driven-development to implement each task.

**Goal:** Bind new independent clinical attestations to verifiable source-file fingerprints without storing clinical source files in hospital accounting SQLite.

**Architecture:** Add immutable nullable metadata to G3A clinical attestation and a one-way per-department policy. Hash supplied multipart bytes on the server while attesting atomically; verify later by re-hashing an authorized re-upload. Preserve reference-only behavior for departments not yet opted into new control.

**Tech Stack:** Python FastAPI, SQLite, vanilla JavaScript, pytest-style script tests, TestClient, Playwright/Chromium.

**Spec:** `docs/superpowers/specs/2026-10-31-clinical-source-document-fingerprint.md`

## Tasks

- [x] 1. Add real TestClient policy/source-hash API RED tests for authorization, correct vs wrong bytes, no content retention, direct DB constraints and invoice issue.
- [x] 2. Add schema/migration with encrypted pre-DDL rollback detection and genuine frozen G3A fixture test (RED->GREEN), preserving old witnesses and records.
- [x] 3. Implement minimum clinical opt-in + multipart hash attestation/verification API and shared atomic write path; run tests green.
- [x] 4. Wire clinician and owner pilot UI actions. Test mobile/desktop Chromium where available; retain privacy warnings.
- [ ] 5. Run source-wide CI/regression, inspect git diff, write QA/known risks and package reproducible ZIP + source-history Bundle with manifest/hash and unpacked smoke.

## Constraints

No clinic source bytes, original filenames, credential details or patient data written to ledger/audit/export or bundled files. Never deploy/migrate hospital production. Missing historical V8.0 remains BLOCKED, not passed.
