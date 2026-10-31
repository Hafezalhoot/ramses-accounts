# Ramses Project Autopilot — durable handoff

- Current development version: `V8.1E-G2Q` — 31 Oct 2026 — no production deployment.
- Source baseline: original G2P ZIP; official frozen-schema fixture under `tests/fixtures/schema_v8_1e_g2p_original.sql` (no private financial records).
- Current state: M0 governance in progress; M1/M2 security partially mitigated; M3 cash and patient finance locally tested partial; M4-M8 medical/inventory/cost modules and financial close incomplete; M9 real network/UAT blocked; M10 not started.
- Implemented this increment: F-012/F-013/F-014/F-015/F-016 targeted mitigations, F-026 keyboard skip link, GitHub Actions smoke workflow (authored only), local Git history with G2P baseline + G2Q changes.
- Test evidence: `QA_G2Q_TEST_RESULTS.tsv` with 76 PASS, 3 SKIP, 1 historical V8.0 archive FAIL. Also `python3 scripts/ci_smoke.py` and static checks.
- Constraints: not connected to a matching GitHub accounting repo; did not push/deploy; previous Ramses medical-contracting repository is a different project; no secrets or patient data in release.
- Next unblocked work: full role/department/fund RBAC → bed stays and dated tariffs → inventory and clinical resources/doctor accruals.
- Blocking dependency for historic upgrade: genuine `Ramses_Accounts_V8_0_Double_Entry_Decision_Foundation.zip`; place in `tests/fixtures/` or set `RAMSES_V80_ARCHIVE`. Never manufacture a mock ZIP.
- Release sign-off remains NO GO: professional accountant, IT administrator, department operators and independent recovery/UAT required.
