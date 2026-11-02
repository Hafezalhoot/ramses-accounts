# S8 - historical cashier identity, test-only

## Defect and business impact

The cashier screen and the hospital cash-day report currently derive historical shift display names from the last schedule version. After an owner schedules a future name change, an older shift may appear under the later name (or blank for a retired custom code). That is a misleading audit label, not a change to the underlying amounts.

## Accepted slice

- The shift list and cash-day summary return `shift_name` resolved from the *effective-dated version at each shift's `business_date` and linked point*, with safe legacy code fallback. Do not guess based on today's/latest plan.
- Preserve existing `shift` code, session ID, accounting figures, role scoping, and no new GL transactions, migrations, or changes to historical schedules.
- The RTL desktop, mobile and daily-report modal display the server's shift name; the latest schedule remains authoritative only for creating a **new** shift.
- Test a custom name for one shift today with an approved future renaming, list + summary API, browser desktop/mobile/modal and HTML encoding. Test old code fallback and zero mutation.

## Explicit exclusions

No supplier 2200 close rule without accountant-signed policy; no production data, electronic medical/financial posting, new roles, balance adjustment or hospital deployment. Synthetic HTTP/Chromium are not physical workstation acceptance.
