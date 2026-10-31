# G3E Inventory Visibility Implementation Plan

> Implement inline on a local isolated branch, test-first; no deployment.

**Goal:** Close unauthorized patient-case reference exposure in warehouse overview and approval APIs.

**Architecture:** Reuse existing point-access policy in `billing.case_scope`. Filter overview issue/return rows at SQL level with one shared predicate; recheck reviewer case scope inside approval transaction. Add one API-level regression using synthetic SQLite.

**Tech Stack:** Python, FastAPI, SQLite, existing source-owned HTTP test scripts.

**Spec:** `docs/project-autopilot/G3E_INVENTORY_PRIVACY_SPEC.md`.

**Global constraints:** No schema changes, no real hospital data, no production deployment, no entitlement expansion; owners retain existing visibility.

**Review focus:** Missing grant, revoked grant, two points with disjoint grants, still permitted unlinked issue, unauthorized approval must not alter source/GL.

### Task 1 -- Test the patient scope boundary

**Files:** Create `tests/test_v82_g3e_inventory_privacy.py`.

- [x] Write a real TestClient/SQLite test that logs in owner, clerk, reviewer; creates cases for two distinct points, stock evidence and both a case and standalone issue; removes point B permission and asserts only authorized case rows are returned.
- [x] Assert owner sees all; reviewer receives 403 when approving point B after grant revocation, while point A and unlinked documents remain permitted and the unauthorized journal is not posted.
- [x] Run the test on unmodified G3D, capture the expected failure.

### Task 2 -- Fix once at the authorization boundary

**Files:** Modify `inventory.py` only.

- [x] Implement shared `visible_issue_scope()` for the current owner/stock-user model, used to filter both issues and returns in SQL rather than filtering only client-side.
- [x] Enforce `case_scope()` inside the issue decision transaction before posting accounting entries.
- [x] Re-run the new regression RED to GREEN, then test previous G3D inventory/returns behavior.

### Task 3 -- Release evidence and state

**Files:** Update `scripts/ci_smoke.py`, `PROJECT_AUTOPILOT_STATE_AR.md`, `CURRENT_RELEASE.md`; create G3E QA report.

- [x] Execute syntax checks and all runnable project tests (including CI gate), record skips/blockers separately.
- [x] Package source and Git history with SHA-256 and verify archive extraction; retain NO-GO status until field, backup and historical migration gates are met.
