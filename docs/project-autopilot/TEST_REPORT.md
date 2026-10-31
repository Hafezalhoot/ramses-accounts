# G3A — verified local development tests (2026-10-31)

- 109 individually invoked `tests/test_*.py` scripts on frozen G3A source: **103 PASS, 3 SKIP due to missing G2J/G2K/G2L historical source, 2 SKIP due to intentionally excluded private workbook, 1 BLOCKED due to unavailable genuine V8.0 archive, zero functional failures**. Every status is in `QA_G3A_TEST_RESULTS.tsv`.
- G3A new tests: `test_v82_g3a_clinician_identity.py` and `test_v82_g3a_role_upgrade.py` PASS (including negative access, revocation, encrypted rollback, existing old G2Z session/attestation, and real SQLite FK check).
- Chromium UI (stubbed synthetic backend): clinical screen 320, 375, 1440px; owner identity review 375, 1440px PASS. Includes phone sidebar menu reachability. This is not live integration with hospital APIs.
- Endpoint dependency inventory: 187 API routes, 186 guarded with `Depends(get_user)` and 1 public `/api/login`; inventory is NOT a complete authorization or object-level security certificate.
- CI: 37/37 PASS في تشغيل منفصل (31 أكتوبر 2026); actual execution log `QA_G3A_CI_RESULTS.txt`.
- Historical V8.0 migration, private June workbook, original predecessor upgrade snapshots, offsite restore and hospital UAT were NOT executed.

---
- G2Y local CI smoke: **33/33 PASS**, `QA_G2Y_CI_RESULTS.txt`; historical V8.0 still BLOCKED, not green.
# G2Y — Verified local test run, Oct 31, 2026

105 scripts: 99 PASS, 3 SKIP historical source, 2 SKIP missing private workbook, 1 BLOCKED missing V8.0 original; 0 functional fails. Recorded in `QA_G2Y_TEST_RESULTS.tsv` and `RAMSES_V81E_G2Y_REPORT_SCOPE_QA_AR.md`. New API test demonstrated real fund leakage RED then GREEN; Chromium role-switch RED then GREEN. Not a hospital UAT or offsite restore.

---
# Ramses Accounts — G2X local synthetic verification, 31 October 2026

- Branch: `fix/g2x-restricted-shift-authorization`, starting G2W `35f22cd`. NO-GO production; no deployment or real data.
- TDD reproduction: `test_v82_g2w_shift_fund_scope.py` failed on G2W on `GET /api/shifts` revealing synthetic restricted shift, then passed with current grant, approval split and immediate revocation.
- Second full runner: **104 files = 98 PASS / 3 SKIP missing prior-version source / 2 SKIP private workbook / 1 BLOCKED missing V8.0 original / 0 FAIL**, process exit 0, details `QA_G2X_TEST_RESULTS.tsv`.
- CI: **32/32 PASS**, process exit 0, `QA_G2X_CI_RESULTS.txt`.
- Initial runner: 97 PASS, 5 SKIP, 1 BLOCKED, **1 FAIL**: `test_free_preview_e2e.py` expected anonymous GET 401 but status not captured. The same real localhost HTTP test passed twice in isolation and in the second complete runner after adding a health identity assertion and detailed status diagnostics. Cause of first failure unresolved; track further sporadic status/port issues.
- Fresh syntax: Python compileall, JS `node --check`, Bash `bash -n`, `git diff --check` (see release verification).
- Not run: genuine V8.0 historical schema fixture, two older previous snapshots not included, private June reference workbook, live multi-user UAT, external/offsite encrypted restore, production browser or real deployment.
