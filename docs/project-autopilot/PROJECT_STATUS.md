# Ramses Accounts — Stabilization S2 (TEST_ONLY)

Date: 2026-11-02 (Africa/Cairo)
Source baseline: G3N-S1, commit `1c35cb57812b0cde6670b7d1a5e3f07c95e550be`.
Working branch: `stabilization/s2-cashier-acceptance`.
Operational status: **STAGING / NO-GO PRODUCTION**. No hospital data was used, no live DB migrations were applied, no release was deployed, and no accounting policies were changed.

## Implemented and locally verified

- 24-hour synthetic cashier operation across night (100 EGP), morning (200), evening (300), and central treasury: independent receipt approval, blind counts, independent cash handovers and accounting closure; 600 EGP transferred, 50 EGP central expense, 550 EGP final treasury; source external cash zero; balanced GL and correct revenue once.
- Cashier partial treasury deposits now accept `client_request_id` as an optional stable retry token. Duplicate keys with matching payload/user replay the **existing** voucher; mismatched payload/user rejected 409. All checks and posting use the same `BEGIN IMMEDIATE` SQLite transaction. Ordinary vouchers retain their own independent request-key namespace.
- Physical source shift + trimmed case-insensitive note is treated as one unique envelope/handover reference even when a retry uses a new token. Additional installments need distinct original references.
- The accepted real handover receiver, if the current internal treasury cashier, can complete treasury receipts directly through the existing shift screen, including after independently approved external shift closure, before a newer external shift takes custody. Server rechecks all permissions. New action uses role-informed `can_treasury_deposit` / remaining amount response.
- Fixed an existing UI defect: cashier shift schedule slots previously lacked `end`, causing literal `undefined` in the shown clock; recompute per-point effective slot end and label internal one-slot schedules to end of day.
- Confirmed 375/1440 px Chromium UI with real FastAPI TestClient/SQLite bridge (not real HTTP transport). Synthetic tests only; no production deployment.

## Not verified / release blockers

1. Original actual V8.0 archive was unavailable, so historical migration/backup and opening balances remain unaccepted.
2. No real-browser-to-HTTP/TLS, WAF, reverse proxy, trusted device or physical LAN tests. Chromium loopback is administratively blocked in this sandbox; TestClient bridge is not a substitute.
3. No independent off-device encrypted restore, hardware failure drill, financial officer approval, clinical workflow sign-off, or 24-hour real staff pilot.
4. Payment source documents and patient/doctor verification are not independently authenticated. External reference transcription and operator input can still be wrong; a changed/falsified physical reference cannot be reliably detected without signed/evidence-matched custody documents.
5. Existing API callers omitting `client_request_id` still work for backwards compatibility but cannot replay their **same** prior result by token. However identical physical `source_shift_id`+`note` is rejected even with a new token.
6. A client UI retry token survives network errors while the current page remains open, not a full browser/device restart. The physical-reference conflict blocks the same reference being booked again but requires reconciliation if a confirmation response was lost.
7. Supplier control ledger vs GL (2200) is not yet a signed period-close policy; insurance, pharmacy/drug stock, multi-store, surgeon contracts/fee splitting and approved medical discharge policies are not part of S2.

## Next 3 executable gates

- S3: independent, secured staging network smoke with actual cookies, CSRF, TLS and per-role controls at 375/1440; real device acceptance.
- S4: add late-entry/envelope scenario spanning external shift handover, unallocated cash, physical custody evidence, day-journal, supplier bank, patient invoice and period close; compare subledgers to GL with a finance reviewer.
- S5: restore a verified original V8.0 encrypted archive on a separate machine and reconcile opening balances, then obtain finance/medical/IT sign-off.

All new functionality beyond stabilization remains frozen until those P0 gates are evidenced. See `TEST_REPORT.md`, `DECISIONS.md`, and `ROADMAP.md`.

---

## Historical project record — preserved from S1 source

# G3D local status — 2026-11-01

- Branch: `feat/g3d-case-consumables-returns`, baseline G3C commit `2a5d2ee`.
- Scope: immutable original-lot FIFO returns (independent approval and reversing posted GL); net case costing; pending return month/case clearance blocking; direct SQLite defenses.
- Verified encrypted G3C source migration and rollback locally on synthetic fixture. Full final regression 120 = 114 PASS, 5 SKIP, 1 BLOCKED missing genuine V8.0, 0 FAIL; Separate CI 45/45 PASS exit 0; source-archive check tracked independently.
- No live database, hospital users, external push, deployment or real patient details. NO-GO.

Next 3: (1) complete regression+CI and reproducible source ZIP, (2) authorized physical return inspection/quarantine and corrected bills/PO/AP, (3) off-device restore and finance/clinical/IT UAT including missing genuine V8.0 source.

---

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
