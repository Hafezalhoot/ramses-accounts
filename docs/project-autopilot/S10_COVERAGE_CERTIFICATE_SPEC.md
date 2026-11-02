# S10 — Completion of a cashier day with non-operating points

Status: approved project continuation scope, synthetic local testing only.

## Problem

`shift_coverage.report` already calculates effective-dated expected windows, grace, and missing/unclosed alerts correctly for points with schedules. It marks points whose approved plan does not operate on a particular weekday as `not_required`. However `/api/shifts/day-summary` currently considers *every* point on that day in `all(status == 'complete')`. A single deliberately non-operating point makes a fully closed active cashier day appear incomplete and provisional.

## Acceptance

1. A business day is `shift_coverage_complete=True` if at least one monitored required point is `complete` and every other point is either `complete` or `not_required`. No financial certification is implied (`financially_certified=False`).
2. A required missing, open, submitted, variance, upcoming or grace shift keeps the day provisional. Unknown coverage (`not_monitored`) also keeps the day provisional; no new claims of completeness.
3. Existing source-of-truth expected shifts, absence warnings, effective-dated custom schedules, accountant month-close gates and finance journal logic remain unchanged. No database migration.
4. UI labels for deliberately off-duty (`not_required`) points are human-readable in full-coverage view. No new page.
5. Validate via real FastAPI auth, independently with a synthetic SQLite fixture containing a fully closed active point and at least one off-day point. Record read-only DB invariants and basic regression.

## Options considered

- Change all `not_required` days to `complete` in the reporting module: rejected because it misrepresents station shifts which were not scheduled.
- **Use the existing `not_required` status as a neutral element in the day-summary aggregate**: chosen; minimal change, no financial posting.
- Introduce new state/schedule tables or add a dashboard: rejected as complexity unrelated to the defect.

## Limits

This does not certify accounting transactions, prove a missing shift did not operate in paper, authorize any payroll or money movement, or replace hospital operations UAT.
