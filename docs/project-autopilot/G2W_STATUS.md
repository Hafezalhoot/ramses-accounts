# Ramses Accounts G2W — GL read-scope hardening (2026-10-31)

Baseline: G2V encrypted upgrade; development/test only, no production deployment.

Implemented: default `viewer` is denied global ledger trial balance (JSON/CSV) and global journal detail list. `owner`/`reviewer` retain access. This is a restricted security slice, not a hospital-wide RBAC completion claim.

Evidence: tests/test_v82_g2w_gl_viewer_scope.py observed 200 before fix, 403 after fix on synthetic TestClient data. Six local regression scripts passed: G2W GL scope, G2U privacy, G2Q security, G2N bank grants, G2I accounting safety and G2U cross-month billing. Full 102-script suite NOT rerun for G2W; historical V8.0 fixture missing.

Risks: global trial balance and general journal visibility for `reviewer` still requires a signed chief-accountant policy; other accounting exports and dashboards need independent route-level scrutiny. Do not operate on real finance/patient data. Next: approved role matrix, scoped or aggregate finance views, clinician execution sign-off, supplier AP lifecycle.
