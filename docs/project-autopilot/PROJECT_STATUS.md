# G3C Project Autopilot verified state — 2026-10-31 (local source only)

- Baseline G3B commit `4933339`; local isolated branch `feat/g3c-case-consumables-cost`; NO production access or deployment.
- IMPLEMENTED: case-scoped approved FIFO consumables report with two independent access checks; pending/unlinked excluded; real Chromium query at 320/375/1440 with stale response replaced after revocation.
- IMPLEMENTED: chronological FIFO approvals check same-item later-approved issue by business date (API plus SQLite triggers). Deliberately keeps day-resolution same-day approvals in transaction order; no historical changes or new GL.
- IMPLEMENTED: frozen original G3B schema upgrade with authenticated encrypted `.rbe` pre-DDL backup, isolated restoration, no extra archive on a second start.
- Full source QA independently rerun: **116 scripts; 110 PASS / 5 SKIP unavailable history/private source / 1 BLOCKED missing V8.0 / 0 FAIL, 0 TIMEOUT.** See `QA_G3C_TEST_RESULTS.tsv` and technical report.
- CI smoke: **42/42 PASS (exit 0)** in `QA_G3C_CI_RESULTS.txt`. ZIP extraction and Git bundle verification are additional release gates reported independently.
- NO-GO production. Reports exclude drugs, unlinked supplies, opening stock, clinical salary, doctor fees, insurance and total case profit.

Next three:
1. Medical source issuance, per-case material returns/reversals and independently approved FIFO corrections, without historical silent mutation.
2. Vendor PO/invoice/AP, clinician billing governance, and insurer/doctor settlements.
3. Genuine V8.0 + historic G2J/G2K/G2L archives, external recovery/UAT, and finance/medical/IT signoff.

---

# G3B Project Autopilot verified state — 2026-10-31

- Git baseline: G3A `885e80e`; branch: `feat/g3b-clinical-document-fingerprint`; NO shared push or hospital deployment.
- IMPLEMENTED locally: independently attested source SHA-256/size/media, clinician signed-in upload/verification, department opt-in owner/password, SQLite immutable guards, invoice-time enforcement, migrated genuine G3A schema with pre-DDL encrypted backup, responsive pilot UI.
- Regression: 112 run, 106 PASS, 5 SKIP historic/private, 1 BLOCKED missing genuine V8.0, 0 FAIL, 0 TIMEOUT. Historical G2J/G2K/G2L `SKIP ` stdout corrected instead of falsely counted as PASS. See QA_G3B_TEST_RESULTS.tsv.
- Source file is transiently read and may be spooled to OS temp disk. No clinical source persisted in accounting tables. This is not evidence of professional licensing, validated source retention or legal signature.
- CI independent 39/39 PASS (exit 0); 3 Chromium browser test scripts PASS. Source-archive evidence will be recorded in `QA_G3B_RELEASE_VERIFICATION.txt` when issued.
- Production gate: NO-GO. Real off-device restore, medical/finance/IT signoff, professional licensing, secured HIS document custody, missing genuine historical source, complete case costing and hospital UAT outstanding.

Next three:
1. Independent medical identity/signature approval, clinical source custody policy, short-lived file/upload and privacy audit.
2. Governed remediation for historical unbilled reference-only/legacy viewer witnesses, with human audit and no silent DB rewrite.
3. Case-linked operating room/NICU consumables and suppliers/doctors/insurance subledger followed by independent hospital UAT and offsite restore.
