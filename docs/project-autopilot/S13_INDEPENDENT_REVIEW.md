# S13 independent read-only review

Reviewed against base `a4485e0c8854308b65df960b526290cf958ec507` and the current uncommitted source. Scope: `print_documents.py`, router registration, billing/shift print links, local Cairo loading and assets, print CSS/JS, S13 API test, updated G3J typography test, and `scripts/qa_s13_cashier_demo.py`. Requirements: `docs/project-autopilot/S13_CASHIER_PLAN.md`.

The checkout and Git state were not mutated by this reviewer. No private files, environment files, application data directory, credentials, or live preview were read. Isolated API checks created temporary synthetic databases only.

## Current assessment

No outstanding Critical or Important defect found in the reviewed print source after the fixes below. The reviewed API slice is consistent with existing object permissions, blind-count behavior, and independent handover/close. This is not a production-readiness assessment. Actual PDF/physical-printer visual acceptance remains with the executor's browser run; the independent Chromium launch terminated with SIGABRT before loading a page.

## Strengths

- Invoice printing authorizes the case with `case_scope`; receipt printing calls `collection_receipt`; shift printing calls `shift_daily_report`. Existing point/fund checks and current grant revocation are retained rather than reimplemented.
- Stored text passes through `html.escape(..., quote=True)` in all print fields/tables/titles. The few interpolated money strings are generated from numeric database piasters, with a constant redaction string for `None`.
- Print GETs perform SELECTs only. The API regression verifies unchanged audit, journal, fund-movement, voucher, invoice and collection counts, with balanced GL and no foreign-key violations.
- Original invoice amount and current remaining due have distinct Arabic labels. Issuance versus payment, cash versus electronic methods, submitted count versus final close, and TEST ONLY status are explicitly explained. Latest receipt additions at `print_documents.py:68-77` identify the original invoice, collection station, cashier and historical shift after the existing receipt authorization; every resulting value still passes through escaped fields.
- Local Cairo 400/600/700 assets are present with OFL license and provenance. The TTF OS/2 weights and cmap coverage for the Arabic document text were checked independently; the updated served-asset typography test passes.

## Findings resolved during review

1. **P2 — Handover state printed as absent after acceptance.** `print_documents.py:102` (originally line 94) originally translated `accept`/`reject`, while `app.py:1488` persists `accepted`/`rejected` and `shift_daily_report` returns those values. A closed accepted shift therefore said `لم يُستلم بعد`. Current keys use `accepted`/`rejected`; `tests/test_s13_cashier_print.py:86` checks acceptance and `:110` checks rejection. Independent re-run observed reader status `accepted`, shift status `closed`, and printed `تم الاستلام`.

2. **P2 — Existing G3J typography regression rejected local fonts.** `tests/test_v82_g3j_cairo_typography.py:8` originally asserted the removed Google loader. Failure was reproduced. The current test exercises same-origin styles, real TTF headers and license; re-run PASS.

3. **P2 — Narrow print width exceeded the selected 80 mm page's content area.** `static/print.css:7` originally combined 10 mm page margins with a 72 mm receipt width, leaving only 60 mm on 80 mm paper. Current named receipt page uses 4 mm margins, consistent with 72 mm content. Source fix reviewed; actual PDF rendering not independently observed.

4. **P2 — QA helper could not resume after a failed clinical attestation or after opening treasury before handover.** `scripts/qa_s13_cashier_demo.py:74` saved the line before attestation, and the old `:99` unconditionally reopened treasury whenever handover was incomplete. Current `:75-80` checks/retries evidence separately and `:104-106` reuses a saved treasury shift. These fixes were reviewed in source; the live helper was not executed by this reviewer.

## Current actionable recommendations

- Nonblocking: preserve the mixed-method corrected-receipt print check in a checked-in regression, alongside existing G2H coverage. The independent injected check passed: original case and total retained, destination case absent, cash/POS parts labeled, and correction warning shown. Location: `tests/test_v81e_g2h_receipt_reassign.py:144`, immediately after reading `old_receipt`.
- Nonblocking: `scripts/qa_s13_cashier_demo.py:30` rewrites the credential/checkpoint JSON in place. An atomic write to a same-directory temporary file created with mode 0600, followed by replacement, would improve interrupted-run recovery and keep permissions safe before content is written. No credential exposure was observed in the reviewed source.
- The helper uses explicit opt-in, reads credentials only from private files, checks the matching HTTPS trycloudflare URL and `free-preview` environment, and defaults evidence to a private directory. Its checkpoint approach does not establish exactly-once execution if a POST succeeds but its response/checkpoint is lost; the executor should reconcile server state before replaying an uncertain mutation.

## Verification performed

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tests/test_s13_cashier_print.py` — PASS, including the latest accepted/rejected handover assertions, reviewer point revocation, and restricted-fund grant allow/revoke sequence.
- Updated `tests/test_v82_g3j_cairo_typography.py` — PASS.
- Additional isolated reviewer check: restricted fund print 403 without grant, 200 after granting, 403 after revoking — PASS. Also checked invoice/receipt point revocation for reviewer — PASS.
- Existing G2H receipt-reassignment API scenario with temporary additional print assertions — PASS, re-run after the latest receipt metadata changes. Corrected receipt retained original historical case AND invoice numbers and mixed cash/POS total, with correction notice and no destination case/invoice exposure.
- TrueType metadata/cmap inspection — Cairo weights 400/600/700 and Arabic document character coverage PASS.
- Independent isolated Chromium/PDF attempt — unavailable: browser process exited SIGABRT before navigation. No PDF/visual PASS is claimed here.

## Existing behavior / declined to judge

- Existing clerk ownership access to historical shift details remains in `shift_daily_report`; removal of a point assignment alone does not revoke that existing historical custody reader. This was not introduced by S13 and was not broadened by print.
- The JSON daily report's original blind-count redaction and movement visibility were preserved. This review does not redefine that existing accounting policy.
- Private preview identities, credentials, account seeding and actual live evidence were explicitly excluded by the review request.
- FIN-01/month-end policy, hospital UAT/signatures, procurement and insurance lifecycle, off-device recovery and real fiscal document compliance remain outside the S13 print slice.


## Coordinator closure and visual evidence

The two nonblocking recommendations are closed: corrected mixed-receipt printing is now checked in `tests/test_v81e_g2h_receipt_reassign.py` and passes; the QA helper uses a mode0600 same-directory temporary file, flush/fsync and atomic replace for checkpoints. Checkpointed existing treasury shifts and clinical evidence are reused. Exactly-once recovery after an unknown POST outcome is not claimed.

Parent verification:154 scripts =149 PASS/5 SKIP/0 FAIL; CI78/78. Actual external HTTPS cashier UI journey and Chrome375/1440 print flows PASS; protected-owner login/reload/session check separately recorded. Three final PDFs were rendered to PNG and inspected: invoice and shift summary one A4 page each, receipt one80mm page; no clipping observed. Accepted receiver label is present. No physical printer/POS acceptance performed.
