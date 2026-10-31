HISTORICAL ARCHIVE: an additional owner decision on 2026-10-30 defines the physical internal/main treasury, outside cash remittances, central-origin expenses, provisional draft custody, financial variance exceptions, optional photos, in-app dashboard notes and a shift calendar. Use `V81E_CENTRAL_TREASURY_OWNER_DECISIONS.md` for all these cases. This archive is not authoritative for implementation.

# وثيقة تاريخية مؤرشفة — غير معتمدة للتنفيذ

هذه نسخة تفكير أولي سبقت توضيحات المالك. لا يُستخدم وصفها لثلاث ورديات ثابتة لكل نقطة، ولا تعليمات «إدخال يومية ورقية تفصيلية/إجمالية» في أي تطوير جديد. القرار الأحدث في `RAMSES_V81E_COMPLETE_SHIFT_CASHIER_PLAN_AR.md`: الخارجي 3 ورديات حاليًا، الداخلي 1، والجداول مرنة، وكل العمليات إلكترونية؛ صور الورق والظرف للإثبات أو الطوارئ. احفظ هذه الوثيقة لأغراض التتبع التاريخي فقط.

**تنبيه مهم — وثيقة P0 تاريخية وليست المرجع النهائي للمرحلة.** بعد توضيحات المالك في 30 أكتوبر 2026، المرجع الأساسي هو `RAMSES_V81E_COMPLETE_SHIFT_CASHIER_PLAN_AR.md`:

- الخارجي 3 ورديات، الداخلي **وردية واحدة** وليست 3؛ عدد الورديات لكل نقطة قابل للتعديل.
- كل معاملات المرضى والفواتير والتحصيلات والمصروفات تُسجل **إلكترونيًا**؛ الورقة وصورة الظرف فقط لإثبات إقفال/طوارئ. لا ننشئ قناة إدخال فواتير ورقية مستقلة أو نُرحّل إجماليات ورقية تلقائيًا.
- تظل V8.1E-P0 مراقبة تجريبية للورديات الثلاث الافتراضية إلى حين تنفيذ P1. الأقسام التالية تصف التفكير التاريخي وتُقرأ فقط مع الخطة الجديدة.

---

# Ramses V8.1E - Shift-first cash operations and delayed-paper reconciliation

**Decision**: 2026-10-30, hospital owner. **Status**: architecture approved; read-only coverage MVP implemented in V8.1E-P0, financial retrospective posting and envelope workflow NOT implemented. Development/testing only; never use with actual patient or hospital money yet.

## 1. Authoritative hierarchy

A shift is the smallest operational reporting slot:

Hospital -> active cashier collection point (external, internal, future) -> business date -> expected shift slot (night, morning, evening) -> actual shift session OR documented paper-only/late-entry packet -> individual patient receipts, invoices, advances, expenses, payment channels and cash-custody transfers.

Three slot starts default to **00:00 night, 08:00 morning, 16:00 evening** in Africa/Cairo. A business date is the **local date the shift begins** (night at 00:00 belongs to the NEW day), never the date of data entry. These are configurable and must use effective-dated schedules; freeze each day's expected slots after publication. Shifts belong to **the cashier point/fund, not to an employee's permanent job title**. Multiple staff may cover a point; one employee may staff different points with authorized handovers.

- Each point's daily statement is all its expected shift slots, including missing and expressly non-operating slots, not only rows already stored in `shift_sessions`.
- Hospital daily statements aggregate all monitored collection points; later weekly/monthly statements aggregate the same unique ledger events without double counting.
- Do not silently use zero for a missing shift. Missing is **UNKNOWN / INCOMPLETE** until evidence is reconciled.
- The default is three expected shifts per active point/day. Owner-approved coverage exceptions or scheduled changes make it two/one/zero; the system must not invent nonexistent work.
- Record expected coverage from a station's owner-approved monitoring start date; do not falsely mark dates before a station opened. If date coverage is unknown, label **not monitored**, not complete.

## 2. Two-layer statuses, never conflate

**Operational/shift slot:** upcoming; running/not yet entered; ended in grace; absent electronic entry; open late; cashier count submitted; physical handover accepted/rejected; accounting review pending; closed independently; planned non-operating; unresolved documentary exception. One actual shift may have a money/cash status and a separate documentation-completeness status.

**Daily point status:** in progress, incomplete, under review, complete, or historical coverage unknown. **Hospital day** is complete only when every monitored point/day is complete or has a documented owner-approved exception with all relevant financial controls resolved. Do not label complete simply because all currently registered rows are closed.

**Important**: missing electronic entry never proves that the employee was absent or that zero receipts occurred. The paper daily sheet and sealed envelopes may contain substantial unentered activity.

## 3. Detect missing electronic shifts intelligently

Required persisted schedule model (future work): station activation effective date; effective-dated shift definitions and point-specific operating calendars; immutable expected-slot snapshot (point_id, business_date, shift code, planned start/end, schedule version); approved no-operation exceptions (author, reason, evidence, scope, approved_by). Unique key (point_id, date, shift code). Support owner configuration of monitoring grace in minutes and escalation rules; never auto-adjust a past schedule when the global template changes.

For each expected slot:

1. Before its scheduled start: upcoming, **no alert**.
2. During operation or within configurable grace after end: in progress/entry due, **no critical missing alert**.
3. After end + grace with no electronic shift or linked paper packet: **not electronically registered**. Create a deduplicated follow-up task for the assigned team/owner.
4. If paper packet is attached but its patient documents are not yet entered: **paper packet received - awaiting entry**, not blank shift and not reconciled.
5. If shift exists but is open after end: **unclosed**, distinct from absent.
6. If physical count/handoff is submitted but accounting is not signed: **awaiting review**, distinct from absent.
7. If owner-approved no-operation applies: **no operation with documented reason**, not missing and not counted as zero revenue by inference.
8. If the shift has detailed accounts but custody evidence is incomplete: **unreconciled custody**, block final certification.

In-app alerts with deduplication (one task per expected slot), owner/reviewer summary, scope-aware cashier tasks, configurable aging and escalation, no notification storm. Optional external alerts require a later explicit decision; none are implemented now.

## 4. Shift-first delayed registration; physical envelope second

Each day starts from the expected slot, not an artificial backdated cash shift. For an old missing slot, choose **register historical paper shift**. Record the *original* service/receipt/payment event date, the actual system entry timestamp, original receiving person, entry operator, paper reference, actual custody holder, proof of cash count and delivery, and selected point. Existing chronological shift restrictions remain untouched.

**Paper detail mode**: list patient identifiers, invoice/service references, actual receipts and methods, advances, expenses with supporting receipts, transfers and refunds. Do not recognize service revenue on a mere payment.

**Paper summary mode**: capture paper totals (cash patient receipts, POS, wallets, bank, advances, cash-paid expenses, other receipts/payments) and envelope evidence first. Save as an **unallocated/documentation-pending** packet; later append patient-level details. Do not fabricate patient invoices, service revenue or unverified expenses from summary totals. One shift can mix detailed and summary lines; preserve provenance per line.

**Envelope/custody record**: immutable reference and counted physical cash, custodian/location (locked drawer, named responsible, hospital safe), documentation status, actual counted time, handover events, sealing information and linked shift allocations. One envelope may span multiple shifts, and one shift may use multiple envelopes; use allocation links and constraints against double allocation. Distinguish a verbal report of custody from a signed acknowledgement. If money was moved between safe and drawer, it is a transfer, not new income.

**Do not produce false historic signoffs**. When no independent counter actually verified an old envelope, record one-person count and a pending independent verification. Late arrival of an employee does not make that employee the original cash receiver.

**Backdated reconciliation decision**: for each old receipt determine whether its cash has (a) already been posted, (b) never been posted, (c) unknown. If (a), allocate/reclassify it with an audit trail **without increasing physical cash**. If (b), post exactly once after approved evidence. If (c), hold as a pending exception; do not post until resolved. Use idempotency and reference checks. For a closed accounting month, correction is posted in an open period with explicit original occurrence date and linked source voucher; never silently mutate past ledger or a closed shift count.

## 5. Accounting totals and correct daily formulas

Distinct measures, always displayed separately:

- Invoiced/earned patient service revenue by valid recognition date **not** equal to payments.
- Actual patient cash received and electronic paid, split by the receiving shift and payment method, without counting transfers as receipts.
- Advances received (liabilities), not revenue.
- Cash operating expenses actually paid from the shift/envelope, separated from expense recognition if the invoice is accrued or another person paid from personal money.
- Cash expected after movements = physical opening + cash receipts + actual external funding - cash expenses - refunds - cash transferred out + transfers in; do not add the same cash when it moves across funds.
- Physical counted amount, variance and custody reconciled amount with separate statuses.
- Totals for day/point/hospital should count each immutable payment part or voucher **once** via unique reference, never by summing opening/closing till balances across shifts.

A missing shift makes the day's actual receipt totals a **PARTIAL figure** and its completeness false, never a statement that missing transactions equal zero. Monthly closing should expose all expected slots and unresolved paper/envelope packets before any final signoff. Maintain as-known-at-close snapshot versus subsequently corrected views and full adjustment provenance.

## 6. Usability: three views, not twenty

1. **Shift Coverage Control Center** - matrix days x points x three shifts with statuses and counts; filters date/month, collection point, fund, expected shift, assigned employee, status, time overdue, envelope and evidence completeness. Desktop table, mobile per-point/day cards, drill-down to shift/paper packet; red attention is action-oriented, not only decorative.
2. **Single Shift Workspace** - view normal or historical shift, receipt/expense rows, paper detail/summary toggle, attach evidence, show invoice/advance links, reconcile custody; save drafts freely without financial posting; clear blocking warnings.
3. **Envelope & Reconciliation Queue** - evidence and custody moves, matching with posted cash and receipts, duplicate checks, deficits, reviewer queue and owner escalation. The point/day/hospital report links to these same records.

Dashboard overview: counts of missing electronic shifts, overdue open shifts, independent reviews, undocumented packets, unallocated cash, envelopes awaiting recount and point/day completeness percentage. Indicate **not monitored** coverage separately; never present a false 100%.

## 7. Approved RBAC M3.5 integration

Multi-role employee accounts may create and verify preliminary data at different points as specifically authorized, but **cannot independently approve self-entered financial activity**. Review is role- AND scope-aware and immutable once posted. Shift ledger views for clerks are scoped to assigned collection points and must not disclose blind expected count amounts. Only owner may grant subdelegated role management (default OFF); this delegation cannot bypass maker-checker on financial data. All changes audited.

## 8. Migration & compatibility constraints

Existing V8.1C `shift_sessions` currently stores only actual sessions with unique date/shift/fund and initial current shift templates; V8.1C reports only actual rows. No migration may create fictional old shift records or alter frozen count/ledger; versioned expected schedule is a new table. Historical dates before activation are unknown until owner reviews them. Preserve existing invoice, collections, GL and cashbook controls and standalone two-person handover. No default enabling of strict clock, no real patient data, no production launch.

## 9. Incremental implementation status / sequence

- [x] **P0** Read-only `GET /api/shifts/coverage?month=YYYY-MM` compares expected point/day/shift slots to current `shift_sessions`, displays missing/open late/awaiting review/closed and not-monitored, filters by point and day status in the Shifts UI; existing day-summary API now carries `is_provisional` and coverage. Scoped to assigned point for clerks. No financial mutations. Standalone backend and simulated Chromium tests pass.
- [ ] **P1** Owner-approved effective-dated station calendars and shift snapshots, active/inactive exceptions, explicit monitoring start, no-operation approval, reliable historic schedule changes; configurable grace and deduplicated alert task dashboard.
- [ ] **P2** Historic paper shift packet creation, attachment/upload, summary/detailed/mixed line workflow, patient service/invoice links and expenses, documentary completeness checklist, no artificial backdated actual shift.
- [ ] **P3** Envelope custody accounting, evidence and sealed envelope allocation across shifts and days, physical counts and signed custody changes.
- [ ] **P4** Reviewer matching and idempotent ledger posting, deposits, refunds, already-posted cash allocation, month-closed corrections and auditable as-of statements.
- [ ] **P5** Hospital day/month/annual certified completeness, reconciliation trend reports, configurable escalations, concurrent cashiers and transaction/invoice tests, accessible RTL desktop/mobile production QA.

## 10. Acceptance scenarios (required before production)

- Oct 29: night closed + morning recorded but awaiting review + evening missing -> point day incomplete, missing visible, provisional hospital total.
- Night 00:00-08:00 belongs to Oct 29, not Oct 28; changed schedules never relabel past records.
- Future evening and current running/grace shift never flagged missing prematurely.
- All three shifts absent on active point/day -> three missing slots after end+grace; a scheduled owner-approved no-operation interval does not produce false alerts.
- Slot has a paper packet but no electronic transactions -> pending documents, not ZERO or CLOSED.
- Employee absence + substitute collector + sealed envelope with different data entry operator -> original cash custodian preserved.
- One sealed envelope for two shifts, two envelopes for one shift, partial transfer to safe -> exact allocation, no duplicate receipt/revenue.
- Paper summary only -> physical custody and unallocated packet recorded, no manufactured patient invoices or revenue.
- Cash previously posted as unallocated -> assign to patient without cash duplication; unknown posting -> hold for review.
- Cash expense from receipts vs employee personal reimbursement -> correct cash and liability treatment.
- Bank/POS/Instapay are excluded from the physical cash envelope and matched to electronic clearing separately.
- Partially entered shift, missing paper reference, duplicate patient receipt, self-review, and closed-month adjustments are blocked or reviewed per policy.
- Non-assigned cashier cannot see a different point or blind expected balance; signed reviewer cannot approve their own cash handoff.
- Test simultaneous edits, double-click retry, interrupted saving, migration on old V8.1C data, and full backup-restore.

## P0 documented limitations

The current read-only coverage demonstration uses the **first recorded shift for each mapped fund as the provisional monitoring start date**, since old stations do not have activation timestamps. Earlier days are **not monitored**, not cleared. It uses the CURRENT shift template to estimate historically unrecorded shift windows; correct versioned expectation history is P1. No automatic live notifications, paper documents, envelopes, approved no-operation, late posting, or certified hospital-day complete status have been implemented. The system still remains TEST ONLY.
