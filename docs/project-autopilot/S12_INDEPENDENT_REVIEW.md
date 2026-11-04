# S12 independent read-only review

Reviewed the working-tree changes against base `0acb2db3aea4dd0de8f2debf880e221dc824b31b` on `stabilization/s12-request-limits-preview`. HEAD remained at the base during review. Scope: `app.py`, `bootstrap.py`, `request_limits.py`, and the two S12 tests; requirements inspected for parser compatibility. No private files, environment files, user credentials, or user email accessed. No checkout mutation or external sync performed.

## Strengths

- The ASGI receive wrapper counts actual body bytes, including requests without Content-Length or with understated Content-Length. Declared excess is rejected before receive or multipart parsing.
- The 7 MiB request cap preserves actual 6 MiB evidence uploads, while the existing 6 MiB per-file rule remains effective.
- Runtime SQLite connections use `mode=rw` and never create missing storage; initialization still deliberately creates storage. URI quoting correctly handles spaces, `#`, `?`, and Arabic characters. Background synchronization uses the same noncreating runtime path.
- The targeted tests exercise real FastAPI parsing, upload spools, attachment writes, synthetic SQLite integrity, session recovery, and rejection without changed financial-row counts.

## Issues

### Critical

None found.

### Important — P2: Restrict the supported parser dependency baseline

- Location: `request_limits.py:34-36`; dependency declaration: `requirements.txt:1`.
- The new limit raises Starlette HTTPException from the body receive function and relies on MultiPartParser closing partial spools for that exception. Installed Starlette 1.10.0 does this, but the existing dependency range also permits Starlette versions through 1.5.1 whose cleanup catches only MultiPartException/OSError. On those otherwise permitted installations a streamed over-cap multipart request skips explicit file cleanup, leaving partial uploads dependent on garbage collection. This violates SEC01's deterministic cleanup requirement and can retain temporary-file resources under repeated requests.
- Official tagged source establishes the transition: [1.5.1 parser](https://raw.githubusercontent.com/Kludex/starlette/1.5.1/starlette/formparsers.py) catches `(MultiPartException, OSError)` at line 267; [1.6.0 parser](https://raw.githubusercontent.com/Kludex/starlette/1.6.0/starlette/formparsers.py) catches `BaseException` at line 267 and closes files on request-stream failures. The official [release history](https://raw.githubusercontent.com/Kludex/starlette/main/docs/release-notes.md) lists 1.6.0 immediately after 1.5.1. Thus 1.6.0 is the first released cleanup baseline identified.
- Fix: explicitly require a compatible Starlette version with that cleanup behavior. Exact tested pins `fastapi==0.162.0` and `starlette==1.10.0` are preferable for this security-sensitive baseline; pin the installed/tested python-multipart version as well if preserving the complete tested parsing stack. A lower bound `starlette>=1.6.0` is justified for cleanup by source, but the review has not integration-tested 1.6.0.

### Minor

None worth blocking this change.

## Verification

Both passed using `.venv/bin/python -B`, with FastAPI 0.162.0 / Starlette 1.10.0:

- `tests/test_s12_request_limits.py`
- `tests/test_s12_runtime_database.py`

Additional isolated probes passed:

- Huge decimal Content-Length values, long leading zeros followed by excess length, duplicate Content-Length, negative length, and empty length were rejected without receiving a body or entering the inner app.
- Configured background sync against a nonexistent synthetic database parent raised SQLite OperationalError without creating a database/directory or attempting an external sync.

The older-parser compatibility conclusion is from official tagged source inspection, not execution of the full app under old dependencies. Full-suite validation belongs to the parent task and was not duplicated.

## Declined to judge

- External mobile-preview protection and its user/email authorization: parent owns that separate workflow; no preview configuration or user identity inspected.
- Global concurrency limits, network upload timeouts, and application-server receive-buffer sizing: separate transport/resource controls beyond this per-request parser-bound change.
- Broader financial policy and schema correctness: unchanged by this diff; targeted rejection tests verify the specified no-write invariants only.
- Intentional database creation by bootstrap/explicit initialization: expressly allowed by SEC03, so not treated as a runtime-storage regression.

## Assessment

**Ready to merge: With fixes.** The current tested runtime meets the reviewed SEC01/SEC03 behavior. Close the parser dependency compatibility finding before treating those properties as guaranteed on all supported installations; no other actionable defect found in the reviewed diff.

## Follow-up review and closure

The P2 dependency finding is **closed**. `requirements.txt:1-3` now pins `fastapi==0.162.0`, `starlette==1.10.0`, and `python-multipart==0.0.33`; independent package-metadata inspection confirms these are exactly the installed versions used for the targeted verification. The supported installation therefore includes the parser's BaseException spool cleanup.

Additional changes reviewed read-only:

- `scripts/seed_preview_demo.py:35-36` uses an HTTPS TestClient origin for both maker and checker. This makes Secure session cookies available to the seed flow without weakening `RAMSES_SECURE_COOKIES`; the isolated database guard and actual user/API authorization flow remain in place.
- `tests/test_s12_secure_preview_seed.py` independently passes with Secure cookies set to `1`, three fabricated approved vouchers, one fabricated reviewer, successful integrity/foreign-key checks, and a repeat call that skips duplicate seeding.
- `tests/test_s12_runtime_database.py:29-42` now moves/restores the whole database parent directory, preserving WAL/SHM sidecars. The revised test independently passes and better models storage loss/restoration.
- `scripts/qa_s12_http.py` reuses the existing loopback Uvicorn transport and separates process-local parser instrumentation from ordinary TCP request assertions. Its child runs use only disposable synthetic storage and disable external mirror settings via the test fixture.

The reviewer independently reran all three current S12 test scripts after these changes: **PASS**. Attempting the real-TCP wrapper stopped before Uvicorn startup because the review sandbox rejects the loopback `socket.bind` call with `PermissionError`. This is an environment limitation, not a failed application assertion; real-TCP completion remains with the parent's ongoing validation. No live preview, private storage, user identity, email, or credentials were inspected.

No additional behaviors were set aside beyond the previously listed review boundaries.

**Final ready-to-merge assessment: Yes for the reviewed code, subject to the parent's normal full-suite/CI/TCP gates.** No open actionable findings remain. The dependency closure addresses the only review finding, and the subsequent HTTPS seed/test-fixture changes are narrow and supported by passing targeted tests.


## Coordinator evidence addendum — 2026-11-04

Parent final gates passed:153 scripts=148 PASS/5 SKIP/0 FAIL, CI77/77,21 S12 TCP requests and161 S4 integrated-day HTTP requests. Three current regression scripts were also checked RED on untouched S11 source, then GREEN on S12.

A later independent password gateway replaced the failing external email-broker route; this deployment configuration was validated by the parent, outside the independent code review above. Anonymous/wrong credentials are denied401; correct gateway and application login/session return200. Real external HTTPS Chromium375/1440 passed login, reload, a delayed session check, Secure/HttpOnly, RTL/Cairo and layout/JS checks. The shipped macOS Apache template was syntax-validated; native-server CVE/production certification is not claimed. See S12_RELEASE_REPORT_AR.md for all limits and retained unsuccessful attempts.
