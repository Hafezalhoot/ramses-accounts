# S5 Cashier HTTP contention test implementation plan

> For agentic workers: use executing-plans and test-driven-development for changes that affect production behavior.

**Goal:** Record and investigate intermittent HTTP 500 during concurrent cashier point assignments using one disposable SQLite database.

**Architecture:** A separate, test-only Uvicorn process, authenticated synthetic users and concurrent independent HTTP connections. Persist error trace and reconcile result counts with the database. No changes to production files without root-cause reproduction.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, requests, SQLite WAL.

**Spec:** `docs/project-autopilot/S5_STRESS_SPEC.md`.

## Global constraints
- Keep finance, permissions and accounting immutability unchanged.
- Avoid patient and employee identifiers, secrets, real accounts and external connections.
- Use disposable database only; no prod migrations or money movement.
- Never claim HTTP failure fixed if source is not established.

## Review focus
- Same owner request repeated concurrently, no duplicate permission row.
- SQLite busy/locked surfaced as HTTP 500, trace preserved for diagnosis.
- Other user role cannot assign point, must stay 403.
- No one thread shares mutable `requests.Session` state.
- Database integrity and FK check pass after concurrent requests.

### Task 1: Build repeatable authenticated HTTP contention probe
- [x] Write test-only script with isolated DB and multiple concurrent HTTP sessions.
- [x] Run and capture status/latency/server trace; verify permission idempotence.
- [x] Re-run at varied concurrency while checking database integrity.

### Task 2: Follow observed failure evidence (conditional)
- [x] Identify root cause from actual traceback and minimal repro.
- [x] Write failing test (RED) for identified path.
- [x] Implement minimum fix and verify (GREEN).
- [ ] Complete full source CI and 141-script QA on a dedicated runner (S5 local run timed out after 5/66 observed successes; eight targeted scripts and S4 acceptance passed).

### Task 3: Release evidence and continuity
- [x] Update status, risks and test report with exact observed results.
- [x] Commit to new S5 branch and package with SHA, verify after unzip and git clone.
- [x] Keep production NO-GO and original V8.0/off-device/LAN gates explicit.
