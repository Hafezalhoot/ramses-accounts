# V8.1E Owner Decision Lock - Central Treasury, Provisional Handover and Shift Calendar

Date: 2026-10-30 | Status: **Approved owner requirements, planning only; NOT IMPLEMENTED**.
Authoritative operational addition to `RAMSES_V81E_COMPLETE_SHIFT_CASHIER_PLAN_AR.md`, replacing superseded open questions in that document and the archived `SHIFT_FIRST_DAILY_MONITORING_PLAN_V81E.md`. The older P0 read-only coverage is not reliable for the actual internal one-shift point.

## A. Actual hospital operations: three different flows into and out of central treasury

**Internal cashier point = central/main hospital treasury (al-khazna al-raeeseya/al-dakhleya).** Its office and physical cash drawer are independent of any external cashier drawer. It is not merely a patient-facing internal cashier:

- External cashier night, morning and evening shifts collect patient payments and make **physical cash handovers to the central treasury**.
- The central treasury **also collects direct patient payments** for inpatient wards, surgery, NICU/incubators and related services, linked to their patient accounts/invoices.
- The central treasury pays hospital expenses from its **whole physically available cash pool**, including notes previously delivered from outside shifts. The source of banknotes does not change the cash-payment ownership of an expense.

**Money classification is mandatory:** patient receipt/revenue (at the originating patient service/collection), external shift -> main treasury transfer (cash custody transfer only), treasury direct patient receipt, and hospital expense paid from main treasury. The expense is **posted to the main treasury's cashier/accounting period, never charged to an outside shift** merely because its cash came from outside. Expense **cost center/benefiting department** is a separate field; it may be any real department supported by evidence, but the source fund remains main treasury. Expenses paid from personal money are different from main-treasury expenses.

Do not confuse 'one internal accounting day' with one employee having a 24-hour work shift. The internal 00:00-24:00 aggregate permits multiple actual cash custody records, deposits, receivers and staff transfers during that day. Physical drawer handover is distinct from operational shift/daily accounting closure.

### Confirmed current starting configuration; every setting is owner-editable

| Collection point | Expected accounting coverage now | Cash location | Historical changes |
|---|---|---|---|
| External cashier | Night 00:00-08:00; morning 08:00-16:00; evening 16:00-24:00, Cairo time | External drawer/fund(s), not central drawer | Owner may change count/names/times to e.g. two 12h shifts, with effective-from date |
| Internal + central treasury | One daily accounting period, 00:00-24:00 | Independent central treasury drawer | Owner may split into two/three shifts and assign personnel, funds and permissions, with effective-from date |

Every effective-dated point/shift/fund/staff setting and old expected slot persists in historic views even after a point or a fund is disabled. Do not retroactively hide outstanding records. Actual patient receipts, expenses and the real custody transfers all retain original transaction timestamps, true entered-at timestamps, actor IDs and independently applicable accounting dates.

## B. Concrete accounting invariants and an example

Assume central treasury opens at zero. Outside shifts collect EGP 10,000 from patients (already accounted as patient receipt in outside shift), and transfer the same physical EGP 10,000 into central treasury. Main treasury collects EGP 5,000 from its own patients, then pays EGP 3,000 of hospital expenses.

- New cash received **from patients** by the hospital = EGP 15,000, not 25,000.
- Outside -> main EGP 10,000 is **one internal cash transfer**, not a second patient receipt or earned service revenue.
- Main treasury cash movement = +10,000 transfer +5,000 own patient collections -3,000 its expenses = +12,000.
- Hospital consolidated reports aggregate the unique original patient receipts and valid expenses, **not** the transfer as new hospital income; the external point's report shows its original receipts and transfer out, and the main fund shows transfer in separately.

Carry money as integers in piasters, with stable invoice/payment/voucher/shift/transfer IDs and idempotency across APIs. POS/bank/wallet clearings never enter a physical cash drawer. Receipts from patients are not automatically earned service revenue; advances are liabilities. The GL and physical-custody subledger must reconcile: an already posted outside patient cash receipt is never posted a second time when the treasury gets it. A real physical transfer can be acknowledged before the originating shift's accounting review is complete; mark source allocation/review pending, use approved clearing rules if necessary, and reconcile the eventual posting once, never hide the discrepancy or manufacture cash.

## C. Two independent dimensions: actual custody versus accounting acceptance

**Dimension 1: physical cash handover**: no handover -> count submitted as draft -> receiving party re-counts actual cash -> receiver's provisional cash acceptance (or documented no-receiver exception and independent verified next-opening count) -> physical custody now belongs to receiver for the amount actually accepted.

**Dimension 2: shift accounting review**: open/late entry -> draft counted -> submitted for review -> review pending with or without variance -> either final closed matched, final closed with approved explicit variance exception, or returned for correction. These statuses are separate and must never collapse into a single 'closed' Boolean.

- **A provisional handover is not a provisional fiction**. It records receiver, giver, counted actual amount, date, time, physical location and references, even when accounting review remains incomplete; it can permit the next cashier shift to run with its own verified opening amount. No one may sign for a colleague retrospectively. If receiver absent, authorized documented exception + separate drawer/verified opening count is necessary to avoid overlapping custody.
- **Drafts are editable but every revision is immutable/auditable**: revision number, actor, server timestamp, reason, before/after money, linked images, original counted-at time. No hard-delete or silent replacement of old revision. An accepted handover cannot have its physical amount overwritten via edit; change requires a new linked correction event.
- **Important 10,000/9,500 shortfall test**: when expected is EGP 10,000 but the receiver actually counted and accepted EGP 9,500, the central physical fund balance rises by **9,500 only**. The difference EGP 500 is a distinct unresolved variance on the outside source shift, not imaginary cash in central treasury. The next shift can open only on real counted cash. The old shift remains under review.
- Final review should not lock cash that was already physically accepted and available for hospital operations, but must expose outstanding control/GL reconciliation and protect subsequent balances. A handover draft alone, without actual acceptance or verified exception, must NOT make cash spendable in the receiver fund.

## D. Shortage resolution and accountant/owner authority

Any discrepancy, including EGP 1, is visible. Ordinary final closure is blocked pending an authorized resolution. Three paths:

1. Verified recount and evidence-based correction: keep old counts and review history, record why they changed.
2. Employee makes up missing cash from personal funds: create a **separate referenced receipt** (source = shortfall settlement), never a patient payment or service revenue. Settling cash is not by itself proof of legal/HR fault; appropriate responsibility and offset account need policy and approval.
3. Owner or **explicitly empowered accountant** authorizes accepting the remittance **with a recorded shortfall**: reason, basis, beneficiary account/reconciliation status, supporting evidence where required, and deliberate accounting treatment under approved policy (shortage investigation/receivable/loss account as applicable). Status **'final closed with approved shortage exception'**, NOT 'balanced'. An overage gets analogous recorded handling.

Owner may assign or revoke a specific `approve_cash_variance_exception` (and if appropriate `review_cash_variance`, `submit_variance_resolution`) permission to a user, scoping by fund, point, monetary limit, period and expiry. The permission is **OFF by default**, independent of the job title 'accountant', and never silently enabled by a broad role template. Only a true authorized independent user can approve; neither the shift's cashier nor the original handover actor nor the request maker may self-approve even with multiple roles. Explicit approval/revocation requires owner confirmation, a reason, server-side checks and audit. The RBAC subdelegation privilege remains separately off by default; accountant variance approval is not permission to edit others' roles.

## E. Evidence files and non-annoying alerts

- Upload receipt-day statement image and photograph of the physical envelope if it exists. Both **OPTIONAL by default**: `require_shift_sheet_image=false`, `require_envelope_image_if_envelope_exists=false`. Owner can switch either on/off independently per point, with effective-dated policy; no retroactive disappearance of old attachment requirements or files.
- A missing optional photo MUST NOT block count, accepted physical handover or final accounting close. Particular legally/accounting-required evidence for an exceptional shortfall remains governed by that exceptional approval policy, not the general photo toggle. Secure original upload, author, immutable attachments after approval, access control and backups remain mandatory.
- Show a calm, grouped **Dashboard Observations** area only (no noisy pop-ups, push, SMS or email by default). Default late-close grace is **2 hours after scheduled end**; configurable by owner globally and optionally per point/shift. If unresolved, keep it in the next day's owner summary; user can acknowledge without falsely resolving it. Label missing electronic shift, late-open shift, provisional cash receipt, unresolved shortage, review waiting and genuinely missing REQUIRED evidence separately. Prevent repeated notifications for the same condition.

## F. Full RTL cashier-shift calendar

Provide responsive **month / week / day** views with attractive, readable individual shift chips for each day. Current chips: outside night (sahar), morning (sabahi), evening (masa'i), central/internal treasury. Chip shows localized shift name, time where useful and **text status plus color**, never color alone. Tap/click opens the exact point/shift workspace, cash count, custody, original invoices and attachments as authorized. Filter by point, fund, user, status, missing/overdue/variance, with drilldown to daily point and consolidated hospital report. Render from the **effective-dated expected shift calendar**, never solely existing shift sessions; historic stopped points and missing shifts persist in history. Do not imply an unregistered shift had zero cash.

## G. Retroactive work, corrections and ordinary receipts

All normal patient invoices, receipts and expenses are electronic. Temporary paper at present is only evidence for the ordinary process; after digital-only transition, paper is an emergency exception for outage/unavailability, with individual electronic re-entry later. Do not provide a second 'paper daily invoice entry' system. Maintain separate original service time, payment time, data entry time and posting time. Cases already posted are linked/reallocated rather than collected twice. A prior posted invoice requiring correction uses the independently approved correction/credit-note pathway in section 22 of the master operational plan.

## H. Required implementation stages and release test gates

1. P1: flexible schedule per point with correct 3-outside/1-internal defaults, effective dates, calibrated grace and calendar read-only views.
2. P2: true central treasury collection/transfer/expense classification and multiple actual receipt/transfer operators, staff/fund permissions and custody separation.
3. P3: versioned draft handover + independent physical count/receiving acceptance, including 9,500 of 10,000 provisional receipt, with next shift able to operate on actual cash.
4. P4: variance resolution by recount, employee settlement receipt or owner/accountant-approved variance exception; RBAC grant/revoke with no self-approval; revisions retained.
5. P5: optional evidence defaults, configurable in-app-only alerts, calendar and per-point/central/hospital reporting.
6. P6: safe delayed electronic registration and prior-document correction, zero duplicates with old invoices, transfers or GL.
7. P7: atomic posting, historical migrations, concurrency, authorization, late-closed-month, backup/restore, attachment access and UI acceptance including small-screen RTL.

Minimum end-to-end acceptance cases: (1) 3 outside +1 internal, (2) future schedule 2x12h with unchanged historic missing shift, (3) outside EGP 10k -> main EGP 10k and direct-internal EGP 5k / expense EGP 3k, (4) no falsely attributed outside-shift expense, (5) expected EGP 10k / received EGP 9.5k allows next shift while old shortage remains open, (6) employee EGP 500 shortage settlement distinct from patient revenue, (7) accountant authorized to accept EGP 500 shortage while another user is denied, (8) self-approval denied, (9) photo toggles OFF then effective-dated ON, (10) quiet dashboard summary and calendar preserve stopped historical points, (11) draft revision history immutable, (12) outage re-entry/duplicate and late correction work without false backdates.

No production deployment or live money operations are authorized by this document. As of this revision, P0 remains a read-only experimental coverage checker that assumes 3 shifts per point; the new rules, calendar, draft physical handover, accounting approval and flexible shift schedules are not in code yet.
