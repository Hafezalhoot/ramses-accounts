# G2S M4b — physical bed transfers and month-end accounting

## Trial policy (not hospital-approved)

A bed has occupancy interval `[start_date, end_date)` using local calendar days. A transfer at date D makes the original bed stop on D and the destination bed own D. The time-of-day and partial-day policy is **not configured**. This must be signed by medical operations and finance before live use.

- Only an owner can enter an administrative transfer, using the original open stay, target bed, date, unique request token and evidence reference. No clinical discharge is inferred.
- Source end-date, target start-date, transfer document, audit and idempotency are atomic (`BEGIN IMMEDIATE`). Every transfer is immutable. Target bed and patient case cannot overlap existing intervals.
- Previously priced nights on the source at or after transfer day prohibit backdating. Controlled financial correction and medical reconciliation will be needed for errors.
- A transfer never creates a voucher, collection, invoice or GL journal. Each nightly rate remains a snapshot of the latest effective service price on that night.
- Month closure requires all elapsed calendar nights within the month to be recorded and to have a posted invoice issued no later than that month end. Patients may remain admitted beyond the month. This is deliberately strict, and a future accrual/interim invoice policy may replace it after accountant approval.
- No historical occupancy, releases or nightly charges can be inserted into sealed months through API or ordinary SQLite SQL. Ordinary database file owners can bypass SQL triggers: off-device audit anchoring and operational access controls remain mandatory.
- Missing original V8.0 source and actual hospital billing policy remain release blockers. NO-GO for real patients or money.
