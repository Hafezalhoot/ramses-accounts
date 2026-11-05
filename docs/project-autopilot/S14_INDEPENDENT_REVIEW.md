# S14 final independent whole-branch review

Base: `30fb06b`; reviewed the current uncommitted S14 implementation on `development/s14-pricing-and-payment-options`, including new untracked implementation/test files. Source was reviewed in passes against the latest `docs/project-autopilot/S14_PRICING_DESIGN_AR.md` and `S14_PLAN.md`.

## Assessment

**No remaining actionable findings in the reviewed S14 scope. Ready for the parent's final gates and delivery.** No critical or important defect was found during this independent pass. This is a bounded code/API/form review, not approval to operate with real hospital data or to launch production.

## Strengths and independently checked fixes

- Accepted line prices, package net allocations, tariff identities and private fee/cost terms are append-only; fulfillment retains agreed prices, and draft/invoice/GL/print readers use the agreed net. Existing clinical proof gates remain at fulfillment and invoice issuance.
- Public-only quote and package-preview hashes bind immutable version references without hashing hidden low-entropy costs or rules. Order acceptance and package publication recompute under `BEGIN IMMEDIATE`; stale results require renewed confirmation.
- The previously pending package-preview finding is fixed at `pricing.py:285-298` and `static/pricing_ui.js:150-175`. An independent real-API probe inserted a new same-price tariff version between preview and publication: the stale hash and an omitted hash both received 409, then an explicitly refreshed preview saved successfully.
- The previously pending whole-package cancellation finding is fixed at `static/billing.js:74-80,290` and `pricing.py:331-343`: the UI shows one control for a wholly ordered package and calls its whole-order endpoint with a reason. An independent real-API probe verified all components become cancelled in one transaction without a new GL journal and that cancellation is refused after a component is fulfilled.
- Fee proposals remain nonposting reads; only explicit individual approvals create Dr5196/Cr2320 journals. Shared fixed fees, collected-basis percentage deltas, independent occurrence teams, stale amounts/hashes, current point/fund scope, maker-checker, independent reversal and immutable decision history are implemented and covered by passing isolated API tests.
- Generic accounting creation/approval/reversal paths consult protected accounts/source documents; 2320/5196 cannot be used to manufacture or erase unassigned liabilities through ordinary manual journals. Receipt correction/credit paths block active fee approvals until independently reversed.
- Five-part receipt UI preserves the existing payment engine. Synthetic real API verification shows advance allocation creates no additional cash, separate receipts remain separate, unpaid AR stays unpaid, and physical till totals include cash only.

## Independent validation run

All commands used repository `.venv/bin/python` and temporary synthetic databases or temporary browser profiles; `PYTHONDONTWRITEBYTECODE=1` was set.

- `tests/test_s14_pricing.py` — PASS.
- `tests/test_s14_service_fees.py` — PASS.
- `tests/test_s14_split_payments.py` — PASS.
- `tests/test_s14_upgrade.py` — PASS; frozen authentic S13 schema upgraded twice, old records unchanged, encrypted pre-upgrade rollback independently restored.
- `tests/test_s14_pricing_ui.py` — PASS at 1440 and 375; synthetic DOM/network fixtures only. Initial sandboxed Chrome startup aborted; the same isolated test passed with approved headless Chrome launch.
- `/private/tmp/s14-final-seam-probe.py` — PASS; extends the maintained full-schema pricing API flow without editing it, adding stale/missing package-preview token rejection, explicit renewed confirmation, atomic whole-package cancellation with no GL and rejection after partial fulfillment.

The parent separately owns the full regression/V8.0 gates and real protected HTTPS browser evidence; this review does not substitute the synthetic UI test for real API/browser integration.

## Bounds and declined-to-judge behaviors

- Actual insurer claim/authorization/settlement, contractual credit limits and cash disbursement of provider payables remain explicitly deferred in the accepted design; they were not judged as missing S14 features.
- Reversal permanently suppresses that occurrence/person/rule from automatic proposals, per the parent's explicit design ruling; rejected proposals are likewise permanently suppressed. No reopen/replacement workflow was inferred.
- Proposed financial performer assignments are independently checked by the reviewer against existing clinical evidence; they are not an automatic claim that the selected person was the medical attester. The previously established clinical identity/document gates were checked for preservation, not redesigned.
- Aggregate fixed fees may exceed discounted net revenue by explicit user policy; the owner gets a negative estimated difference warning rather than an invented rejection rule.
- FIN-01, real hospital acceptance, production launch, tax certification and operational data were outside this review. No private files, `.env`, operational database/data directory or live preview was opened. Source, index, HEAD and branch state were not mutated.

## Follow-up review of final three changes

Independently reread the published-unit guard in `pricing.py:250-261`, responsive pricing rate/package cards and their CSS, session identity/role checks around asynchronous pricing/fee/catalog reads, and `showLogin()` closing the custom dialog. **No additional actionable findings; prior assessment remains unchanged.**

The unit guard executes inside the existing immediate write transaction, locks a service's unit once any managed tariff exists, and still permits description edits with the same unit. Mobile cards escape user text, retain the desktop table representation, expose the same actions, and show rate/discount/net values without horizontal table scrolling.

Validation rerun after these changes:

- Maintained `tests/test_s14_pricing.py` — PASS, including published hour-to-minute rejection (409).
- Independent in-memory extension of that full-schema API test — PASS; a same-unit description edit remains allowed and the unit remains `ساعة`.
- Maintained `tests/test_s14_pricing_ui.py` — PASS at 1440/375, including explicit mobile rate-price bounding box and package-card assertions plus the stale owner catalog response test.
- `/private/tmp/s14-final-followup-probe.py` — PASS at 1440/375; independently adds a late owner fee queue/balance response after switching to a different clerk identity, and a late order catalog after changing the same identity's role from owner to clerk. Neither replaces the new cashier content or opens the old privileged dialog.

These probes used synthetic fixtures/temporary profiles only; no repository source/Git mutation or private/live data reads.
