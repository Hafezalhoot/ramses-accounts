# S5 — Source-first FastAPI / SQLite contention correction (2026-11-02)

**Baseline S4 branch**: `60bddc1`. One isolated temporary SQLite database per independent test. Real Uvicorn HTTP over loopback, no TLS/browser/hospital dataset.

**RED 1 (S4 unmodified `bootstrap.connect`)**: 96 concurrent authenticated HTTP point-assign requests, 16 workers; 14 HTTP 200 / 65 HTTP 500 / 17 network failures. Server traceback: `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread` at billing `assign_point`. 15 audit entries despite 14 acknowledged successes, demonstrating ambiguous outcomes to clients.

**GREEN 1**: `check_same_thread=False`, per-request connection retained. 240/240 at 24 workers, 256/256 at 32 workers, no 500.

**RED 2**: 384 HTTP assignments, 48 workers; 383 HTTP 200 / 1 HTTP 500. Trace `sqlite3.OperationalError: database is locked` at `BEGIN IMMEDIATE`; 10s `PRAGMA busy_timeout` contradicted sqlite3 connection's 30s timeout.

**GREEN 2**: Remove redundant PRAGMA, inherit `timeout=30` => SQLite busy_timeout 30000ms. Final 384/384 HTTP 200, 384 audit events, 12 unique active permissions, 403 denied clerk reassignment, `integrity_check=ok`, zero FK violations. Final p50 0.680s, p95 4.818s, worst 10.035s. These timings depend on this isolated test machine and are not a hospital SLA. Another 384/48 run with explicit 30000 PRAGMA also passed, followed by a 240/24 after simplification.

**S4 integrated day post-final code**: in-process PASS; separate Uvicorn real TCP HTTP PASS 161 requests, patient/cashier, central vault, supplier, bank, GL, protected period-close gate unchanged.

**Eight sensitive regression scripts independently PASS**: `test_user_lifecycle.py`, `test_v82_g2t_concurrency.py`, `test_v82_g2t_revocation_race.py`, `test_v81e_g2j_treasury_integrity.py`, `test_v81e_g2i_financial_safety.py`, `test_v81e_g2m_secure_backup.py`, `test_v82_g2q_security.py`, `test_v82_g2w_gl_viewer_scope.py`.

**Full CI is NOT GREEN IN S5**: `python scripts/ci_smoke.py` hit container execution timeout after 240s; first five lines PASS and no observed FAIL, remaining results unknown/uncompleted. No full S5 141-script QA run executed. Prior S4 full suite evidence cannot substitute for current commit.

**Production NO-GO**: original V8.0 not sourced, no independent off-device restore, network/TLS/browser/workstations not exercised, real employee signoff and financial/medical procedures unapproved. No real monetary or hospital data used.

---

# S4 verified synthetic integrated financial-day acceptance (2026-11-02)

**Status: DEVELOPMENT TEST_ONLY / HOSPITAL PRODUCTION NO-GO.** Source S3 baseline `4e425e490d027922e8b4ab5f43d7aa0c4a2c874f`. Isolated branch `stabilization/s4-integrated-day`. No financial backend, GL rules, schema, production records or deployments altered. A single source-owned synthetic test was added.

## Executed tests and evidence

- `python tests/test_s4_integrated_day.py`: PASS. Same disposable SQLite database connects real patient invoice/collection, night/morning/evening cashier handover, central treasury, historical sealed envelope correction, supplier PO/GRN/invoice and due schedule, independent payment and statement signoff, 2200 attributed payables, GL, bank, and period preflight.
- `S4_REAL_HTTP=1 python tests/test_s4_integrated_day.py`: PASS. Same scenario over a separate Uvicorn HTTP listener on 127.0.0.1 using distinct `requests.Session` cookies; **161 actual HTTP requests**, NOT Chromium, browser, TLS or hospital network.
- Three further sequential repeat runs of the same HTTP test: **3/3 PASS, 161 requests per run**. Their logs are separately captured in test-session QA evidence.
- Full regression `python scripts/qa_g2t_full.py`: 141 total scripts, **135 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT**, exit 0. These are scripts, not branch/statement coverage. Full TSV captured separately.
- `python scripts/ci_smoke.py`: **66/66 PASS**, exit 0. Historical original V8.0 test NOT covered. Detailed CI output captured separately.
- S4 negative gates: denied a cashier self-handover, denied cross-role transfer, rejected altered retry key, unmatched bank statement before signing blocks period close; after signing, settlement confirmation reaches 6000 piasters and 4000 remain as supplier 2200 payable. Real current month close stays HTTP 409. A **test-process-only** simulated future clock proves completed prior-month close, never applied to the HTTP worker or any production instance.

## Accounting result (synthetic, Egyptian pounds)

- Current-day external cashier receipts: 100 real patient invoice + 200 + 300 = **600**. External cash fund ending balance **0** after three independent deposits.
- Historical signed-paper-only invoice 1,500 minus previously cash-paid expense 200 = **1,300** physically received once in current central treasury. Prior closed GL/fund movements unchanged.
- Central real expense 50 yields **1,850** physical central treasury, independently matched; one 100 supplier liability with 60 approved from bank gives **40** remaining 2200 supplier AP; bank starts at 200 and ends at **140**.
- Patient reconciliation and cash/treasury reconciliation both report matched, GL debit=credit, no SQLite integrity or FK errors. These totals reflect one synthetic database, not hospital day-end signoff.

## Known irregularity; not hidden

During **concurrent parallel suite load**, one real HTTP rerun received **500** on the cashier point assignment request early in fixture setup. The source of this intermittent response was not reproducible after the parallel load ended: three sequential 161-request reruns all passed and no financial mismatch was observed. **Root cause NOT ESTABLISHED; do not claim it fixed.** Before real load/UAT, reproduce under deliberate concurrent load with persistent Uvicorn trace output and resolve any actual server error. This is a separate load/resilience gate, not evidence of financial corruption.

## Strictly NOT verified

Original verified V8.0 migration and signed opening balances, independent encrypted **off-device** restore, browser-to-HTTPS through reverse proxy and hospital workstation/network, printers, real money/source documents, medical policy, supplier 2200 month-close inclusion policy, security pen-test and MFA/IdP, finance/clinical/IT signatures. No live system was changed. **Production NO-GO**.

---

# S3 - local real-HTTP proof (2026-11-02)

Source: S2 commit `3e9669229b5ecc3da954416c1a541ff8642ea71c`.
The browser still cannot reach local HTTP (administrator policy), therefore
S3 uses independent `requests.Session` clients to a separate Uvicorn process,
not mocked/TestClient transport. All DBs are ephemeral SQLite with synthetic
funds, users, invoices, shifts and evidence.

## Direct S3 real HTTP results

- cashier_day: PASS; 4 independent shifts, 600 EGP external, 50 EGP central
  expense, 550 EGP main; detailed reports match and outsiders denied.
- deposit_retries: PASS; same request key and two parallel HTTP retries
  produce one voucher; changed amounts/other physical key rejected.
- late_invoice: PASS; old closed-month evidence links to a current-period
  invoice/GL; no fictional historical cash.
- mixed_envelope: PASS; 4500 gross patient invoices, 600 old paper expenses,
  3900 net physical cash, +/-50 EGP tracked in suspense, no double cash.
- http_security: PASS; separate cookies and active CSRF required, 401/403,
  HttpOnly/SameSite Strict, role denial, static HTML/JS through real HTTP.

**Five independently isolated HTTP suites passed (5/5, exit 0)**. See the committed
`QA_S3_HTTP_RESULTS.txt` for source-own outputs and HTTP request counts.
This does not establish real hospital finance signoff or actual TLS/browser
network readiness. Original Chromium loopback attempt still blocked.

## Additional checks

- Updated S2 daily report assertions passed using TestClient and Uvicorn HTTP.
- `python scripts/qa_g2t_full.py`: 140 scripts; 134 PASS + 5 SKIP + 1
  BLOCKED_NO_V80, zero FAIL/TIMEOUT; exit 0. Full source output is
  `QA_S3_TEST_RESULTS.tsv` and `QA_S3_FULL_SUMMARY.txt`.
- `python scripts/ci_smoke.py`: **66/66 PASS (exit 0)**, retained in
  `QA_S3_CI_RESULTS.txt`; historical V8.0 migration remains unverified.
- Counts represent executed test scripts, NOT statement/branch coverage.
- V8.0 original migration, off-device restore, TLS/real browser, clinical
  authenticity and real 24h UAT are explicit **NOT VERIFIED** gates.

---

# S2 verification and evidence (2026-11-02)

## Starting state

- Verified original G3N-S1 ZIP SHA-256 `8287690bd1f69b3f93566a169b14e9c28d09fb3086baf72feca51cda724e670c` and Git bundle SHA-256 `8788d7f122e05ebab06d8f2e47686e47004a31973e40b9a3a4a414332dc98893`.
- Checked out new branch from commit `1c35cb57812b0cde6670b7d1a5e3f07c95e550be` rather than modifying source baseline.

## Executed locally on disposable SQLite

- `python tests/test_s2_cashier_24h_acceptance.py`: PASS (4 closed shifts, 600 EGP deposits, 50 EGP central expense, 550 EGP balance, source 0, one revenue recognition and balanced GL, integrity/FKs).
- `python tests/test_s2_treasury_retry.py`: PASS (initial same-key duplicate produced two vouchers **before fix**; after fix same-key replay returns one, changed amount/wrong identity/changed key with same physical reference rejected 409, simultaneous two-thread retry produced one voucher).
- `python tests/browser_s2_cashier_treasury_ui.py`: PASS, 375 px and 1440 px, real Chromium DOM and JavaScript with browser fetch bridged into REAL FastAPI TestClient/SQLite, two additional positive deposits. No horizontal overflow, no page JS errors. Previously `undefined` shift clock assertion failed and now passes.
- `python tests/test_v81e_p3_main_treasury.py`: PASS (historical external-to-central and settled variance/ledger).
- `python tests/test_v81e_p4_shortage_repayment.py`: PASS (historic 6+4 settlement, immutable records, GL).
- `node --check static/app.js`: PASS.
- `git diff --check`: PASS.

## Wider regression

- `python scripts/qa_g2t_full.py`: **two independent complete runs, each exit 0**: 140 scripts, **134 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL/TIMEOUT**. After final code changes direct S2 and historic treasury scripts passed again. This runner uses `SKIP` for missing predecessor fixtures; it never equates them with passes.
- `python scripts/ci_smoke.py`: **66/66 PASS (exit 0)**. Historical V8.0 migrations are explicitly excluded.
- Browser network HTTP, TLS/reverse-proxy, actual hospital deployment, real banking credentials, V8.0 original upgrade, off-device restore, certified UAT: **NOT EXECUTED**.

Synthetic source screenshots can be found in separate release bundle. All accounts, staff, amounts, bank funds and transactions are artificial.

---

## Historical project record — preserved from S1 source

# G3D final local full QA — 2026-11-01

- Branch `feat/g3d-case-consumables-returns`, 120 unique scripts invoked: **114 PASS, 5 SKIP, 1 BLOCKED_NO_V80, 0 FAIL, 0 TIMEOUT**. Source `/mnt/data/QA_G3D_TEST_RESULTS.tsv`. Full runner exit code 0.
- G3D TDD: immutable original-lot independent physical returns (2 at 1200 piasters = 2400 piasters net decrease); authorization/Idempotency/FIFO as-of dates/month close/financial-case pending closure/double request concurrency/direct SQL; encrypted frozen G3C upgrade/restore; responsive Chromium 1440/375/320.
- Existing legacy tests for billing service day, physical cash movements and daily shift coverage failed at Cairo midnight due UTC/no grace context. Corrected **tests only** and individually reran each 3/3 PASS; final entire suite rerun clean. Original first-run failures are not reclassified into passes retroactively.
- Separate CI suite 45/45 PASS exit 0 (`QA_G3D_CI_RESULTS.txt`); exact extracted ZIP verification remains independently recorded in release report. NO production approval, no offsite restore and no genuine V8.0 source.

---

# G3C QA regression — 2026-10-31

- Real FastAPI RED→GREEN: missing case cost route 404 -> approved two-lot 5600-piaster trace, dual grants and immediate revocation, no patient names or extra GL.
- Real API+SQLite RED→GREEN: historical-date receipt/issue approval incorrectly accepted -> 409 on API and SQLite direct SQL protection, with no new GL or stock allocations after rejection.
- Real Chromium RED→GREEN: missing case-cost search -> responsive 1440/375/320 retrieval and stale-result removal after permission denial.
- Frozen exact G3B SQL: requires encrypted rollback before two new SQLite triggers, restores original schema and users/sessions/stock, no duplicate backup on restart.
- Complete fresh suite: 116 invoked; **110 PASS / 5 SKIP / 1 BLOCKED original V8.0 / 0 FAIL / 0 TIMEOUT**, exit 0. Unexecuted predecessor tests and private workbook tests are not counted as PASS.
- CI smoke independently: **42/42 PASS (exit 0)**. Local source only, not end-user/hospital acceptance. `QA_G3C_TEST_RESULTS.tsv` is the detailed evidence file.

---

# G3B — local synthetic full regression (2026-10-31)

- **112 individual scripts invoked:** 106 PASS, 5 SKIP, 1 BLOCKED_NO_V80; **0 FAIL**, **0 TIMEOUT**. Full stdout-derived report: `QA_G3B_TEST_RESULTS.tsv`.
- 3 historical G2J/G2K/G2L files printed `SKIP ` without colon and returned exit 0; initial runner misclassified as PASS. We audited their captured stdout, re-ran each and corrected all 3 to SKIP. 2 other source-private Excel tests SKIP; genuine V8.0 original archive missing, blocked.
- TDD API: document hash computed from synthetic PDF bytes, owner opt-in/password and blocked old unbilled witnesses, invalid PDF/size/mime, row immutability, direct SQLite insert guard, invoice gate, revoke mid-session, hash match mismatch and audit metadata no-source.
- Genuine G3A fixture upgrade: encrypted rollback key required before DDL, frozen witness IDs and sessions intact, restored prior schema independently.
- Chromium pilot (stubbed synthetic backend) at 320/375/1440 demonstrates uploaded clinical form and owner opt-in; no EHR/HIS integration or legal medical acceptance.
- CI result separately executed: 39/39 PASS, exit code 0; `QA_G3B_CI_RESULTS.txt`. Three independent Chromium scripts PASS; `QA_G3B_BROWSER_RESULTS.txt`.
- NOT EXECUTED: real hospital UAT, genuine V8.0 upgrade, three pre-G3A historical source snapshots, third-party medical registration, original file custody service, off-device restore or live deployment.
