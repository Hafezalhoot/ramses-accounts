# S3 HTTP acceptance implementation plan

> For agentic workers: execute in an isolated local branch with test-first verification.

**Goal:** Test S2 cashier day and late-entry/mixed-envelope flows over real Uvicorn HTTP without changing financial logic.

**Architecture:** Existing source tests remain authoritative. A thin requests.Session compatibility transport maps their TestClient calls to a subprocess Uvicorn server on a disposable SQLite database. A separate HTTP security test covers browser-session-related server checks.

**Tech Stack:** Python FastAPI, Uvicorn, requests, SQLite, pytest-style scripts, curl/HTTP, Git.

**Spec:** `docs/project-autopilot/S3_HTTP_ACCEPTANCE_SPEC.md`

## Global constraints
- Never touch a live hospital DB, make payments, deploy, or change clinical/accounting policy.
- Bind only 127.0.0.1 in isolated tests; discard synthetic SQLite after each suite.
- Real HTTP success must not be misrepresented as successful TLS or browser-to-HTTP.
- Preserve original S2 tests, roles, documents and journals.

## Review focus
- Concurrent HTTP requests reuse one cookie jar: independently verify resulting voucher count.
- Process hangs: server startup and shutdown are bounded; detect early exit.
- Lost/invalid CSRF: financial POST must reject before mutation.
- Evidence multipart upload: no request bodies invented, verify old envelope path.
- Test suite cleanup: no production env keys or persistent synthetic records.

### Task 1: Non-invasive HTTP transport and four acceptance suites

**Files:** Create `tests/s3_http_transport.py`, `scripts/qa_s3_real_http.py`.

- [x] Implement Session-compatible class with shared Uvicorn process, launch after source test fixture DB exists.
- [x] Verify RED: run suite before transport is fully wired; expect rejected path/wrong connection, not financial mutation.
- [x] Wire transport through `unittest.mock.patch` in a fresh subprocess per source test.
- [x] Verify GREEN: run S2 day, retry, G2D mixed, G2B late via separate HTTP listener.

### Task 2: HTTP auth/CSRF acceptance

**Files:** `scripts/qa_s3_real_http.py`.

- [x] In isolated initialized DB, assert unauthenticated 401, cookie attribute shape, missing/wrong CSRF 403 and valid role auth 200.
- [x] Check that security requests do not modify vouchers/GL or shift sessions.
- [x] Verify each guard in a fresh Uvicorn server process.

### Task 3: Regression, packaging and reporting

**Files:** `docs/project-autopilot/TEST_REPORT.md`, `PROJECT_STATUS.md`, `ROADMAP.md`; S3 delivery docs.

- [x] Run full source suite and CI with outputs captured and exit codes checked.
- [x] Independently extract ZIP and rerun S3 after packaging.
- [x] Commit on isolated branch, verify bundle and SHA-256, keep NO-GO production.
