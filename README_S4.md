# Ramses Hospital Accounts - S4 integrated financial day (TEST_ONLY)

Baseline: S3 commit 4e425e4. Branch: `stabilization/s4-integrated-day`.

## What was proved

This release adds a **single-database synthetic acceptance test**, not another financial module or navigation page. The test carries one fictional business day through actual patient billing, three external cashier shifts, internal treasury, a recovered prior-period paper envelope, supplier purchasing and payables, independent bank payment and bank statement signoff. Each operation uses existing application routes and real SQLite transactions.

The **same test** can run (a) inside FastAPI TestClient and (b) through a separate real Uvicorn HTTP server and multiple independent cookie sessions. Real HTTP is TCP on 127.0.0.1; it is **not** HTTPS, a browser-to-server test, a hospital LAN, or a production deployment.

```bash
python tests/test_s4_integrated_day.py
S4_REAL_HTTP=1 python tests/test_s4_integrated_day.py
python scripts/ci_smoke.py
python scripts/qa_g2t_full.py
```

Financial test balances: current-day external receipts 100 EGP from a real issued patient invoice + 200 + 300 = 600 EGP; all passed to internal safe. A historical paper envelope with a 1,500 EGP patient invoice and 200 EGP paper-paid expense contributes 1,300 EGP of physically received cash **once**. A 50 EGP central safe expense leaves 1,850 EGP internal cash and zero external till cash. Separately a 100 EGP approved supplier GRN creates payable, a 60 EGP independently approved supplier bank voucher is matched and bank-statement approved, leaving 40 EGP source-attributed AP and bank book balance of 140 EGP from a synthetic 200 EGP opening.

Checks include fund balances, independent four-shift closure, patient and treasury reconciliation, source-attributed 2200 payable, GL debits=credits, SQLite integrity and FKs, denied outsider access, rejected duplicate cash, and no changes to source records in the already-sealed historical period.

## Period close is NOT a production signoff

Real Cairo clock: current-month close is refused. In the **in-process synthetic test only**, `app.current_month` is temporarily patched to a future month after all documents and approvals are complete. This proves the route's logical preflight and close branch. The real HTTP test deliberately **does not patch or bypass** the month-end clock and therefore does not seal the current month.

In the synthetic fixture only, operating-point lifecycle dates are constrained so a one-day fictional commissioning does not create missing shifts for all remaining days of this calendar month. The previous period is represented as a synthetic closed record and is **not** a real historic V8.0 migration.

## Observed intermittent condition

One actual HTTP 500 occurred in cashier-point assignment **only during concurrent parallel regression load**. A subsequent HTTP retry and three more independent 161-request HTTP reruns passed. The root cause was not established; this is still an open load-resilience risk, not a repaired defect. Repeat with persistent Uvicorn traces under representative concurrency before any production decision.

## Still NO-GO production

Missing: original authentic V8.0 archive and approved opening reconciliation, encrypted off-device restore, real-browser-to-HTTPS/LAN devices and printers, signed source documents, supplier 2200 close policy signoff, medical/finance/IT independent acceptance, protected production deployment and security testing. No actual patient or bank records were used.

See `docs/project-autopilot/S4_INTEGRATED_DAY_SPEC.md`, `docs/project-autopilot/TEST_REPORT.md` and `docs/project-autopilot/ROADMAP.md`.
