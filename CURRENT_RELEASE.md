# Ramses Accounts — source release ledger (31 October 2026)

**Current source:** `V8.1E-G2Q` — Project Autopilot security-foundation increment based on G2P.
**Environment:** local source archive only. DEVELOPMENT / TEST ONLY — **NO-GO for real money or patient data.**

## Implemented (synthetic-data verified)
- F-012: `login_rate_events` per observed socket source and username; separate 40/15-minute per-source cap; failures only, owner on another source not locked out.
- F-013: employee directory hidden from clerk and viewer in `/api/lookups`; owner/reviewer retain payroll review directory.
- F-015: `backup.py` and systemd-compatible `backup_local.sh` now use authenticated encrypted `.rbe` backups or fail closed.
- F-016: SQL triggers deny update/delete of `audit_log` in an ordinary connected SQLite session.
- F-014 (partial): non-demo Google Sheets mirror now requires explicit privacy approval before any remote request; free preview remains bound to isolated synthetic staging sheet.
- F-026: keyboard skip navigation to main content, verified with offline Chromium at 375px.
- G2P -> G2Q genuine frozen-schema fixture tested twice with preserved records.
- M0: local CI smoke command `python3 scripts/ci_smoke.py` and GitHub Actions workflow authored **but remote CI not yet executed**.

## Constraints
- Auth source address depends on trusted ASGI proxy configuration; remote distributed abuse and shared-network throttling require additional controls/MFA.
- SQL triggers do not stop privileged SQLite file owners from tampering; independently stored append-only audit trails required.
- Existing plaintext backups require inventory/secure treatment; script change does not encrypt old files or set up off-device storage.
- Live Git repository/CI, V8.0 migration fixture, real browsers/devices and accountants' production sign-off remain unverified.
- Missing hospital modules: bed occupancy, operations/NICU costing, procurement/inventory/suppliers, physician fees, annual close, full RBAC.

**Evidence:** `RAMSES_V81E_G2Q_AUTOPILOT_QA_AR.md`, `QA_G2Q_TEST_RESULTS.tsv` and the 32-item register updated as `RAMSES_G2Q_FINDINGS_REGISTER.json`.
