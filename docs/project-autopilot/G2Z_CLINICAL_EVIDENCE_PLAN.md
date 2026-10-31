# G2Z Clinical Evidence Gate — implementation plan (TEST ONLY)

**Source:** G2Y commit `405974d`; original G2T audit item G2T-N08 and Sprint 3.

**Goal:** Pilot separate medical attestation of service performance, with current per-department authorization, immutable reference, independent clinical/financial actors, and invoice-time enforcement when explicitly activated. No live patient data or deployment.

**Constraint:** The existing SQLite `users.role` CHECK has only `owner/reviewer/clerk/viewer`. Production-safe role-table reconstruction is out of scope; **pilot clinical attestors are separately granted *viewer* users**, who have NO cashier/reviewer billing write access. This is not yet a first-class clinician role or verified medical identity, and not a medically or legally valid digital signature. Do not imply readiness for real clinical use.

## Task 1 — regression test (RED)
- Add `tests/test_v82_g2z_clinical_attestation.py` covering synthetic owner, reviewer, cashier, attestor viewer, unauthorized viewer, per-department grants, revocation, and immutable audit records.
- Verify a formerly issued draft is blocked after activating clinical policy until attested (including previously fulfilled items).
- Verify owner/reviewer cannot attest while an authorized attestor can; financial staff cannot mark new clinical services fulfilled under enforcement.

## Task 2 — additive model, API and gating (GREEN)
- `schema.sql`: grant, activation and append-only clinical evidence tables/triggers.
- `billing.py`: explicit owner grant/activation; segregated clinical worklist and attestation endpoint; preserve existing price and period rules; block ordinary finance fulfillment for active clinical departments; check missing attestation on *both* draft creation and invoice issue (including old drafts).
- `bootstrap.py`: existing upgrade backup must detect new objects before migration (already checks all CREATE IF NOT EXISTS). Old data never silently marked signed.
- `scripts/ci_smoke.py`: include new test.

## Task 3 — verify and release
- Re-run G2Z test, select regression, full test suite and CI (record exact PASS/SKIP/BLOCKED).
- Build isolated development ZIP, source history bundle, source manifest, report and SHA-256; verify extracted ZIP against manifest and run tests from extracted package.
- Remain NO-GO: licensed clinical identity verification and authorization, clinical supervisor policy, patient access boundaries, hospital UAT, off-device encrypted restore and original V8.0 archive.

## Security refinements discovered during execution

- Before activation, a department grant must never permit early attestation or fulfillment; tested both FastAPI endpoint and the direct SQLite insert guard (RED→GREEN).
- The clinical evidence reference is stored in the immutable, permission-protected evidence table only. Audit details record actor, line and department without copying the reference into potentially broader financial/Google sync logs (RED→GREEN).
- An older free-preview test expected the previous G2Y release string; it now checks the exact G2Z /health identity, without changing server behavior.
- A first-class medically verified role and attachment/signature validation are **explicitly deferred to hospital approval**, not implied by this test-only pilot.
