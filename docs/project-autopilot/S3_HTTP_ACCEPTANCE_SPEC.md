# S3 local HTTP cashier and late-entry acceptance (test-only)

Baseline: S2 commit 3e9669229b5ecc3da954416c1a541ff8642ea71c.

Goal: prove that existing S2 custody, retry protection, and legacy mixed-envelope
paths work through a separate Uvicorn HTTP process with independent client
sessions, real cookies and CSRF, against disposable synthetic SQLite.

Non-goals: TLS, reverse proxy, hospital LAN/devices/printers, historical V8.0
migration, off-device recovery, live operational UAT or changing accounting
policy. Chromium loopback is currently blocked by sandbox administrator;
S2 Chromium-to-ASGI tests remain separate evidence and are not HTTP evidence.

Acceptance:
1. The original S2 full financial day (3 cashier shifts and internal vault)
   is rerun over real HTTP; expected 600 EGP receipts - 50 EGP expense =
   550 EGP vault; GL balanced and independent approvals.
2. S2 partial treasury double-submit/concurrency is rerun over HTTP:
   one physical deposit yields one voucher and no double GL.
3. Historical G2D mixed envelope with patient AR, documented old cash
   expense and variance suspense is rerun over HTTP using multipart evidence:
   no additional cash movement, current-period corrective journal and GL.
4. Historical G2B late invoice with prior-month source is rerun over HTTP;
   existing close/preflight rules remain enforced.
5. HTTP security checks: unauthenticated /api/me 401, post without session
   401, valid session but missing/bad CSRF 403, different user's CSRF 403,
   login cookie HttpOnly and SameSite=Strict, and no claim of Secure under
   local plain HTTP.
6. No modification of production data, server settings, roles or money.
7. A truthful results file distinguishes HTTP tests from Chromium/browser/TLS.

Policy: source tests are executed unchanged via a minimal test transport
adapter, never by modifying the financial implementation to satisfy a test.
If a real business defect is found, add a failing regression test first,
fix the root cause, then rerun source CI and the full regression runner.
