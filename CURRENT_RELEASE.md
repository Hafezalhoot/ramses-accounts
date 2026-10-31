# Ramses Accounts V8.1E-G2V — Encrypted upgrade rollback / TEST ONLY (31 Oct 2026)

**Current local development branch:** `fix/g2v-encrypted-upgrade`; derived from G2U. **NO-GO** for patient or monetary production use. No deployment or connection to hospital database.

- Encryption before schema upgrade: existing older or partially upgraded SQLite databases require an authenticated `.rbe` preflight archive; no secure key means the DDL operation stops without altering historic records.
- Destructive shift-table migration creates an independent encrypted `.rbe` rollback, not a persistent plaintext SQLite file.
- Uses established AES-256-GCM/scrypt G2M backup tooling, with isolated authenticated restore; no silent downgrade or overwrite.
- Only synthetic historical and frozen G2T schema scenarios verified. Fresh G2V QA: 97 PASS / 3 SKIP / 1 BLOCKED V8.0 (101 scripts, 0 functional FAIL); CI smoke 29/29 PASS locally. See QA_G2V_TEST_RESULTS.tsv / QA_G2V_CI_RESULTS.txt.
- Transient sensitive SQLite snapshots may touch local disk during creation; use full-disk encryption in real operation. Existing plaintext pre-upgrade backups remain on user devices until inventoried and safely handled by IT.
- Still NO-GO: signed clinical attestation, full finance/HR report permissions, real offsite restore/UAT, missing V8.0 source, supplier/doctor/insurance subledgers and approved month close.

**G2V references:** `RAMSES_V81E_G2V_ENCRYPTED_UPGRADE_QA_AR.md`, `README_G2V_AR.md`, `RAMSES_G2V_FINDINGS_TRACKER.json`.

---
# Ramses Accounts V8.1E-G2U — Stabilization / TEST ONLY (31 Oct 2026)

**Current development source:** G2U is an additive fix based on the exact G2T source archive. **NO-GO for patient or monetary production use; no deployment.**

- Accounting: bed-night service date and fee period no longer follow admission month; current-period draft/invoice/GL and current-period close preflight are checked with isolated FastAPI+SQLite. Approved G2B historical catch-up retains original price/date and books GL only now.
- Database: additive `billing_case_lines.service_date`; a fulfilled record is immutable (UPDATE/DELETE blocked) without silently backdating legacy facts. Genuine frozen G2T schema initialized twice, preserved old draft and financial period attribution.
- Privacy: staff, fund balance and reviewer bank queue protections plus protected voucher lists, export, dashboard and attachment read gates; current fund grant revocation takes effect immediately. Still NOT a full RBAC audit.
- Evidence: `RAMSES_V81E_G2U_STABILIZATION_QA_AR.md`, `QA_G2U_TEST_RESULTS.tsv` (96 PASS, 3 SKIP, 1 BLOCKED/100; no functional FAIL), `QA_G2U_CI_RESULTS.txt` (28/28 PASS), `tests/test_v82_g2u_*.py`. Historical V8.0 migration needs the genuine archive and remains blocked.
- Unresolved P0: independent clinical attestation; unresolved P1: plaintext pre-upgrade SQLite rollback copies, broad reporting authorization and payment evidence defaults.

---
# Ramses Accounts V8.1E-G2T — Development / TEST ONLY

**Current tested source:** G2T based on frozen G2S; no live installation. New central non-drug inventory supplier receipt and FIFO issue with independent approval and linked balanced GL. See `RAMSES_V81E_G2T_INVENTORY_QA_AR.md`. Tests: 93/97 PASS, 3 historical SKIP, 1 blocked V8.0; CI smoke 25/25 PASS locally (separate run). No producer supplier settlement or pharmacy, **NO GO**.

---
# Ramses Accounts V8.1E-G2S — Development and testing only

## G2S — Project Autopilot M4b (2026-10-31)

- Based on frozen G2R ZIP; new `bed_transfers` immutably links atomic old and new physical stays with one owner-authorized dated transfer document; retry-safe, no financial journal or clinical discharge.
- Month-close now evaluates bed nights by **night_date** even for patients admitted in a previous month. Missing nights and unposted/uninvoiced nights block closure, including closed-period SQLite guards.
- SQL refuses a stale price version when a later tariff was effective at night date. Both transfer and latest tariff requirements have negative regression tests.
- A deliberately excluded private June Excel workbook is not fabricated. `--archive` fails closed; two historical-preview tests will SKIP when the fixture is absent.
- Frozen original G2R SQL schema migration verified twice. See `RAMSES_V81E_G2S_TRANSFERS_QA.md` and `QA_G2S_TEST_RESULTS.tsv`.
- **NO GO for production**: tariffs/month-end accounting and clinical transfer custody await approval. M4c/M6/M5/M7 remain open.

---
# Source release ledger — G2R (31 October 2026)

**Current development release: V8.1E-G2R.** Frozen G2Q source remains the upgrade baseline. No deployment or real financial data.

# V8.1E-G2R — Project Autopilot M4 / bed occupancy and priced nightly orders (31 Oct 2026)

Development-only addition based on **G2Q**; neither installed in hospital nor approved for live patient/payment use.

- New `bed_stays.py` + `schema.sql` structures for inpatient/NICU beds, period-scoped occupancy and immutable nightly service snapshots.
- Owner creates beds and records administrative admission/release only with evidence; cashier/reviewer read solely their authorized patient cases. No clinical discharge approval is represented.
- Date-effective room tariffs reuse the existing service price table; preview shows calendar nights **[start_date,end_date)**. This is a **provisional proposed rule**, NOT approved hospital billing policy; accountant and medical operations must confirm nights, partial days, transfers, payer, exemptions and month-end allocations.
- The owner explicitly orders missing nights as **billing_case_lines in ordered state**. Separate service fulfillment and invoice issuance remain necessary; no cash or GL posted when recording a bed or selecting nights.
- Concurrency constraints and SQL triggers prevent double occupancy, duplicate nights, cross-case snapshot links, unauthorized mutation of night evidence and re-opening financial cases. Financial case clearance blocks open bed stays and unrecorded nights. Same-day zero-night cancellation can still undergo independent no-charge review without fake invoices.
- NICU added as an additive seeded department; existing department IDs and historical records untouched.
- New regression tests: `test_v82_g2r_bed_stays.py`, `test_v82_g2r_bed_stays_ui.py`, `test_v82_g2r_upgrade.py` with frozen G2Q original schema. Test evidence: `QA_G2R_TEST_RESULTS.tsv` in release.

Next work: clinical custody/fulfillment role, signed tariff/partial-day policy, shift/transfer boundaries and long-stay month end; operations/NICU consumables -> inventory/procurement/suppliers -> doctors' fees. Non-production release gate remains **NO-GO**.

---
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
