# Ramses Accounts — G2X local synthetic verification, 31 October 2026

- Branch: `fix/g2x-restricted-shift-authorization`, starting G2W `35f22cd`. NO-GO production; no deployment or real data.
- TDD reproduction: `test_v82_g2w_shift_fund_scope.py` failed on G2W on `GET /api/shifts` revealing synthetic restricted shift, then passed with current grant, approval split and immediate revocation.
- Second full runner: **104 files = 98 PASS / 3 SKIP missing prior-version source / 2 SKIP private workbook / 1 BLOCKED missing V8.0 original / 0 FAIL**, process exit 0, details `QA_G2X_TEST_RESULTS.tsv`.
- CI: **32/32 PASS**, process exit 0, `QA_G2X_CI_RESULTS.txt`.
- Initial runner: 97 PASS, 5 SKIP, 1 BLOCKED, **1 FAIL**: `test_free_preview_e2e.py` expected anonymous GET 401 but status not captured. The same real localhost HTTP test passed twice in isolation and in the second complete runner after adding a health identity assertion and detailed status diagnostics. Cause of first failure unresolved; track further sporadic status/port issues.
- Fresh syntax: Python compileall, JS `node --check`, Bash `bash -n`, `git diff --check` (see release verification).
- Not run: genuine V8.0 historical schema fixture, two older previous snapshots not included, private June reference workbook, live multi-user UAT, external/offsite encrypted restore, production browser or real deployment.
