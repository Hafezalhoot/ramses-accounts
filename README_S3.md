# Ramses Hospital Accounts - S3 local HTTP acceptance (TEST_ONLY)

This is a **development-only** continuation of G3N S1 and S2. Do not run
it on production hospital records. There are no new financial modules or
accounting schema changes in S3.

## What's new

The existing full cashier-day, partial deposit replay, historical late
invoice and mixed cash envelope workflows now have a reusable real-Uvicorn
HTTP regression runner, not just in-process TestClient calls. Separate
cookie-bearing sessions check authentication, CSRF, role denial and static
asset delivery. The original cashier-day test also checks four detailed
daily reports and denied access across shifts.

```sh
python scripts/qa_s3_real_http.py
python tests/test_s2_cashier_24h_acceptance.py
python scripts/ci_smoke.py
python scripts/qa_g2t_full.py
```

Each test uses a new temporary synthetic SQLite file and a locally bound
Uvicorn process (127.0.0.1 on an ephemeral port), stopped after each run.
`requests` is already in `requirements.txt`.

## Verified boundaries

- Actual HTTP requests and separate Uvicorn process: YES (local loopback).
- Different cookie jars, session authorization and CSRF: YES (synthetic).
- Late historical evidence and correction to current-period GL: YES (local).
- Chromium browser reaching the live HTTP server: **NO**, blocked by the
  sandbox administrator. Existing browser-to-ASGI UI suites are separate.
- HTTPS/TLS, reverse proxy, hospital devices, printer, real 24h UAT: **NO**.
- Genuine V8.0 source migration, off-device encrypted restore: **NO**.
- Production readiness: **NO-GO** pending hospital IT, finance and clinical
  acceptance, correct source documents and recovery checks.

The next engineering gate is **S4**: a single database/workday that spans
cashier, patient, old envelopes, supplier bank, independent ledger preflight,
and month close with no unaccounted differences. Five separate local HTTP
scenarios are valuable but do **not** substitute for that combined UAT.

See `docs/project-autopilot/TEST_REPORT.md` and `S3_HTTP_ACCEPTANCE_SPEC.md`.
