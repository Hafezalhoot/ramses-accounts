# Independent S11 diff review

**Baseline:** `49167d9` (S10). **Head:** current uncommitted `stabilization/s11-operational-review` changes on 2026-11-03. Read-only review of `app.py`, `case_settlement.py`, `static/app.js`, CI registration, the portable browser helper and its call-site changes, and all three new S11 backend tests plus the new daily browser test. No checkout edits or full-suite run by this reviewer.

## Assessment

**S11 targeted changes: ready after the parent final suite/CI gates pass.** No remaining blocking correctness, RBAC or financial-integrity regression was established in the reviewed diff. One introduced Python syntax error was found, reported and fixed during review; the corrected Python files compile. **Hospital production readiness remains NO-GO** independently of this narrow development verdict.

## Strengths / correctness checks

1. **Master-data transaction repair is narrow and correct.** Each of `create_fund`, `employee_add` and `add_user` now starts `BEGIN IMMEDIATE` inside the existing connection context (`app.py:2133`, `app.py:2424`, `app.py:3342`, with lines subject to concurrent documentation-only shifts). This fixes the autocommit problem in `bootstrap.connect()` without changing global connection semantics. Entity, GL fund setup and audit are now one commit, and a failed audit cannot leave the reported-created entity behind. Existing owner-only role checks and duplicate handling remain.
2. **Daily exceptions use the existing authorization population.** `cashier_day_summary` derives exceptions from `shift_coverage.report(..., user)` and its scoped `days`, excludes closed shifts, and explicitly adds unknown monitoring days (`app.py:1222-1232`). It does not query a wider point set or synthesize money. S10 off-duty readiness semantics and `financially_certified=False` remain. Missing entries are represented with no session ID, while future shifts stay upcoming.
3. **The UI preserves meaning and escapes dynamic values.** New status/action strings are static Arabic; point name, shift name, fallback status and action all go through `esc`. The report states it is a follow-up summary rather than financial certification or proof of custody. Missing registration is not described as no actual activity (`static/app.js:564-572`). No new write or privileged action was added.
4. **Pending inventory now blocks both clearance modes and stale approvals.** `case_preflight` counts only pending issues for the already-authorized case, includes the count in the response/blockers and excludes it from `no_charge_ready` (`case_settlement.py:54-55`, `:94-98`, `:126-127`, `:140`). Both clearance submission and independent decision already call this same preflight inside their existing `BEGIN IMMEDIATE` transactions. A stock request arriving after a clearance request therefore prevents approval. Inventory rejection remains available while the case stays open, and unrelated cases do not block each other. No schema, amount, GL or cash movement logic changed.
5. **Browser portability is limited to launch selection.** Existing launch arguments are preserved. The new helper supports an explicit browser path, known Linux/Mac installed binaries, then Playwright's normal default. The repeated changes do not rewrite assertions, mock responses or business transport. The helper is test-only and adds no production dependency.

## Review finding resolved before completion

**REV-S11-01 — Important / P2, resolved:** `tests/browser_s1_inventory_asgi_sqlite.py:8-9` initially inserted `from browser_helpers import chromium_options` before `from __future__ import annotations`. This caused `SyntaxError: from __future__ imports must occur at the beginning of the file` and prevented that acceptance script from running. Parent moved the helper import below the future import. An independent `compile()` pass then succeeded for all 51 changed tracked Python files at that review point and the new S11 Python files. Retained here for traceability; it is not an outstanding defect.

## Independent validation

The following were executed by this reviewer in separate Python processes against disposable synthetic SQLite databases, with bytecode generation disabled:

- `tests/test_s11_atomic_master_data.py` — PASS: genuine SQLite-trigger audit failure rolls back all three entities and GL setup; successful retry and duplicate rejection work; FK/integrity checks pass.
- `tests/test_s11_daily_exceptions.py` — PASS: missing, independent review, unknown monitoring and upcoming states; reviewer fund scoping; unauthenticated denial; no finance/audit/session-count mutation by the report.
- `tests/test_s11_case_inventory_pending.py` — PASS: pending issue blocks no-charge/settled readiness and approval-time recheck; rejection clears only the proper case; self-approval denied; unrelated pending cases stay independent; no new money/GL.
- `tests/test_s10_daily_coverage_certificate.py` — PASS: prior off-day neutrality and no false certification remain.
- `tests/test_v82_g2p_case_settlement.py` — PASS: original financial closure maker/checker, no-charge, concurrency and immutable-closure behavior remain.
- In-memory compilation of changed tracked Python and all new S11 Python sources — PASS after REV-S11-01 correction.

No full-suite or browser rerun was performed by this reviewer, avoiding duplication of the parent's gate runs. I inspected the actual browser script and its stored red/green logs: `daily-browser-green.log` reports 375/1440px, actual loaded Cairo, RTL, no overflow and no page errors. That test uses a real Chromium DOM with a TestClient route bridge, and its docstring accurately says it does **not** prove network HTTP/TLS, CSP enforcement at the deployed edge, or hospital LAN behavior.

## TDD evidence checked

- `evidence/S11/atomic-red.log`: failure explicitly lists persisted unaudited user/employee/fund and surviving fund GL mapping; green log matches the successful independent rerun. This is a real database failure, not a mock echo of the implementation.
- `evidence/S11/daily-exceptions-red.log`: the new public field is absent (`KeyError: coverage_exceptions`); browser red separately fails because the actionable exception panel is absent. Both corresponding green logs pass.
- `evidence/S11/case-inventory-red.log`: original preflight incorrectly reports `no_charge_ready=True` while a pending issue exists; green proves both request-time and approval-time behavior plus resolution through the existing independent rejection route.
- CI includes all three new backend regression scripts; the parent owns the final 150-test and 74-script CI run and its final counts. This reviewer does not certify not-yet-observed suite output.

## HTTP helper compatibility

The existing `tests/s3_http_transport.RemoteTestClient` approach is compatible with these S11 backend tests: each imports `fastapi.testclient.TestClient` inside `run()` after creating its temporary database. A wrapper can patch that symbol exactly as S9 does, then invoke `run()` with `runpy.run_path`.

**Required isolation:** run each suite in its own subprocess, or shut the remote server down between suites. The transport singleton binds the first `RAMSES_DB_PATH`; reusing it across tests with different disposable directories would test the wrong database. Always invoke shutdown in `finally`. A loopback Uvicorn pass is real local HTTP and remains distinct from HTTPS/LAN/browser acceptance. No S11 HTTP wrapper existed at the point of this review; if added later it needs its own execution evidence.

## Nonblocking residuals / scope boundaries

- The existing broad `sqlite3.IntegrityError` handlers still label injected audit-integrity failures as duplicate username/code. The repaired transactions now roll back correctly, which addresses the security/integrity defect. More precise operator error classification would improve diagnosis but is not a new S11 regression.
- No test or code here invalidates old sessions on real disaster-recovery cutover, implements a pre-parser request body limit, changes missing-ledger connection behavior, or verifies the real proxy source chain. Those earlier security review items remain separate explicit work; passing S11 does not close them.
- This fix does not reopen already stranded closed cases or invent month-end service/posting/tax policy. Parent's financial review documents the outstanding bed month-end issue. Keep that operational blocker explicit.
- No schema migration was introduced, so no new historical-data transition is required by this diff. The pending-issue guard operates at the application preflight boundary, reusing existing source records and locks.

## Declined to judge

- Actual production acceptance, legal/tax/clinical certification and accountant-approved date policy: outside this targeted source diff, with no institutional signoff provided.
- Live Cloudflare/MFA/proxy behavior, hospital LAN/TLS/printers, independent off-device recovery and authentic production data reconciliation: unavailable external infrastructure and evidence.
- Parent final full-suite/CI results and any subsequently added HTTP wrapper: independent final output was not yet present at the point this report was written.
- Historical V8.0 source migration rerun: parent owns the supplied-archive validation; this review does not repeat it or imply that the genuine source archive is still unavailable.


## Coordinator completion addendum — 2026-11-04

Parent final evidence:150 scripts=145 PASS/5 SKIP/0 FAIL, CI74/74; real TCP/HTTP wrapper executed each S11 test in a separate process. Later mobile visual inspection led to responsive exception cards, caught by a new RED browser assertion then GREEN375/1440; full150 suite was rerun. The dependency update and responsive cards postdate the independent review above and were verified by the parent, not attributed to the reviewer.

See TEST_REPORT.md and evidence/S11/ for exact scope and limitations. Hospital production remains NO-GO.
