# سجل تاريخي للمراجعة — الحالة النهائية

الملاحظات التالية سجل أثناء التنفيذ، بما فيه بندا الباقة اللذان كانا مفتوحين. أُغلقا بعد ربط بصمة المعاينة وإضافة إلغاء الباقة للواجهة، وتحققت منهما المراجعة المستقلة النهائية في S14_INDEPENDENT_REVIEW.md. لا يمثل النص التالي قائمة مشكلات باقية.

---

# S14 backend task review

Reviewed the current uncommitted S14 pricing/billing/fee changes against `docs/project-autopilot/S14_PRICING_DESIGN_AR.md`, including its final binding clarification. Scope: `pricing.py`, S14 schema additions, `billing.py`/`financial_corrections.py` integration, invoice print totals, and `service_fees.py`. All probes used synthetic temporary SQLite databases; no private, environment, production data, live database, or preview content was read. No repository files or Git state were changed by this reviewer.

## Remaining findings

No remaining actionable backend findings after the fixes below were independently checked.

## Confidentiality finding fixed and independently verified

### [P2] Do not expose an unkeyed digest of hidden estimated costs

Location: `pricing.py:169-170` (`full_quote`), with public filtering at `pricing.py:193-195`.

`quote_hash` hashes the entire private line snapshot using plain SHA-256, then returns that digest to the cashier. A hidden estimated cost is low-entropy financial data, so hiding its JSON keys does not protect it: a cashier can reconstruct the known public line, guess the common empty rule list, and enumerate candidate `unit_cost_piasters` / `estimated_cost_piasters` values until the public digest matches. An isolated real API reproduction recovered the hidden 25.00 cost of the 100.00 theatre tariff after only 2,501 guesses. This breaks the explicit cashier cost confidentiality requirement.

Applied fix: `pricing.py:169-172` hashes only public quote terms together with immutable `rate_id` and `package_version_id` references. Independent `/private/tmp/s14-review-cost-fixed-probe.py` verifies the hash equals the public-only encoding and that none of 10,001 private-cost guesses reconstruct it. The full pricing API flow and stale-tariff guard still pass. The maintained pricing test also verifies the public-only token. Fee basis now accepts only `collected`, matching the final user clarification.

Reproducer: `/private/tmp/s14-review-cost-probe.py` extends the existing full-schema pricing API test and prints the recovered cost. It passed against the reviewed vulnerable implementation.

## Findings fixed and independently verified during review

- **[P1] Generic manual GL bypass of payable approval:** 2320 and 5196 were ordinary unprotected accounts, allowing a manual Dr5196/Cr2320 journal to create an unassigned service liability without a fee decision, or a Dr2320 adjustment to erase it without reducing person balances. Parent added these accounts to `financial_integrity.PROTECTED_CODES`. Independent real API probe now receives 409 from `/api/accounting/journals` for the bypass.
- **[P2] Revoked point access bypass on order replay:** priced-order idempotency returned stored line IDs before checking current case/point scope. Parent moved current scope checks before the replay result. Independent full-schema API probe revokes the clerk's point grant and confirms the identical request now returns 403.
- **[P2] Cumulative collection allocation could retract an approved fee:** largest remainder for invoice receipts has the Alabama paradox. With net weights `[1500,1500,900,500,500,200]`, receipt 25 allocated `[7,7,4,3,3,1]`, receipt 26 allocated `[8,8,5,2,2,1]`; an already approved 3-piaster fee on the fourth line remained booked although the recomputed entitlement fell to 2. Independent real API reproduction confirmed it. Fee agent replaced receipt allocation with exact highest-averages/D'Hondt allocation, preserving monotonicity as receipts increase. Updated fee API regression passed independently.
- **[P2] Before-discount percentage lost zero-net rounded occurrences:** legal quantity 2 / gross 200 / net 1 / full collection 1 / 50% `discount_affects=false` produced only 50 instead of 100 piasters because the second occurrence had net 0 and forced fee base 0. Independent real API reproduction confirmed it. Fee agent now prorates each gross occurrence by the line collection fraction; updated fee API regression proves two independent 50-piaster proposals and passes.
- Per-occurrence performer assignment now supports and validates a complete unique 1..quantity occurrence map, and both preview and fee proposals use the assigned occurrence's people.

## Validation

- `repo/.venv/bin/python /private/tmp/s14-review-pricing-probes.py`: PASS; original pricing flow + revoked replay 403 + manual payable bypass 409.
- `repo/.venv/bin/python tests/test_s14_service_fees.py`: PASS after rounding fixes; synthetic fee decision, incremental collection, sharing, rejected/reversed suppression, maker-checker, current point/fund grants, immutable evidence, exact payable GL and no cash movement.
- `/private/tmp/s14-review-fee-probes.py`: independently reproduced both historical rounding defects before the fixes; the maintained test now contains corrected assertions.
- Independent exhaustive highest-averages math check: 24,056 small weight/amount combinations matched a straightforward exact iterative reference and remained monotone.
- `repo/.venv/bin/python /private/tmp/s14-review-cost-fixed-probe.py`: PASS; public-only hash and failed hidden-cost enumeration plus original pricing API flow.
- Original full pricing flow also passed in the cost-leak reproducer, demonstrating why key absence checks alone missed the original confidentiality defect. The corrected hash then passed the independent fixed probe.

## Explicit design rulings from parent

These were considered and are not reported as defects under the current authorized scope: aggregate fees may exceed net service price because fixed fees survive discounts; individual percentages remain limited to 100%; a reversal permanently suppresses that occurrence/person/rule to avoid immediate regeneration; cashier performer assignments are proposed teams that the independent reviewer must validate against existing clinical evidence before approving any payable. Actual cash disbursement remains a later workflow.

## Supplemental basic UI review

`tests/test_s14_pricing_ui.py` independently passed at 1440px and 375px with synthetic DOM/API fixtures and temporary Chrome profiles. Covered owner forms, package preview invalidation, stale quote explicit reconfirmation, distinct per-occurrence teams, fee approval/reversal payloads, clerk restrictions and horizontal overflow. Initial browser launch was prevented by the file sandbox; the same isolated regression passed with the normal approved browser launch.

### [P2] Provide the whole-package cancellation UI (pending parent fix)

Location: `static/billing.js:78`. The case panel correctly hides individual cancellation for `package_version_id`, but no application code calls `/api/pricing/orders/{order_id}/cancel` or renders a whole-order cancel control. Consequently an accepted, wholly unexecuted package cannot be cancelled through the application despite the design and backend explicitly supporting this path. Render one cancellation control per `pricing_order_id` only when all package lines remain ordered; collect a reason, invoke the existing whole-order cancellation API and reload. A focused browser regression should show the control before fulfillment, hide it after any component is fulfilled, and verify the cancellation endpoint/order ID.

## Additional backend stale-preview finding (pending parent fix)

### [P2] Bind package creation to the tariff versions shown by its preview

Location: `pricing.py:284` (`create_package` recomputes `package_preview` without an expected snapshot), together with `static/pricing_ui.js:154` (the UI compares only the input JSON to its last preview request).

Package creation accepts exactly the same input even if the tariffs, costs or fee terms changed since the owner previewed them. An isolated full-schema real API reproduction previewed a one-component package with tariff 100.00 and discount 10.00, obtaining net 90.00; a new 200.00 tariff was then appended; saving the identical package payload succeeded and stored net 190.00. The owner can therefore publish a materially different price without seeing and confirming it. Fixed-final-price mode likewise silently changes the comparison cost, discount and fee rules.

Minimal fix: return a public-terms/immutable-version preview hash, require it when creating a package, recompute under the write transaction and return 409 when it changed. Have the UI refresh the preview and require an explicit second confirmation. Keep the token free of secret low-entropy financial data. Reproducer: `/private/tmp/s14-review-package-race-probe.py`.

The earlier "no remaining actionable backend findings" assessment preceded this supplemental package-builder review; this finding is now open pending its fix.
