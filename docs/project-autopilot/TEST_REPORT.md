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
