# S5: isolate cashier-point HTTP 500 under concurrent load

Scope: local, test-only S4 checkout; no production accounts, no schema or accounting changes without a failing regression. The historical S4 note reported one intermittent HTTP 500 while assigning a cashier point during heavy parallel tests, without a server traceback. Fixing an unproven cause is prohibited.

Goals:
1. Keep an independent Uvicorn server trace while sending authenticated, concurrent HTTP requests that target the real /api/billing/points/{point_id}/assign endpoint.
2. Retain response statuses, latency, exception class, SQLite integrity, and audit counts without logging cookies, passwords or financial/clinical data.
3. If a repeatable failure appears, trace to the source, create a test that fails on S4 and passes after the smallest code correction. If not reproducible, report NOT_REPRODUCED and preserve the original incident OPEN.
4. Validate relevant regression tests and keep S4 baseline unchanged; S5 remains test-only.

Out of scope: production deployment, original V8.0 historical migration, genuine signed restore, TLS/hospital workstation validation, actual patient/bank records.
